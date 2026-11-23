"""Install, uninstall, and status for Plus4 Grease. Python 3.7."""
import collections
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess

from . import VERSION, edits_v160, system
from .edits import FEATURES, Edit

MODEL_FILE = "/dev_info.txt"
MODEL = "QIDI@x-plus_4"
VERSION_FILE = "/root/xindi/version"
# V2.1.1 is what Plus4 Grease is tested on. QIDI shipped 1.8.1 and 1.8.2 only as online updates, so their stock
# files can't be checked; QIDI's published 1.7.1 configs before them and V2.1.1's after them have the same text
# where every edit applies (docs/plus4-notes.md, "Firmware 1.8.x").
SUPPORTED_SOC = ("V2.1.1", "V1.8.2", "V1.8.1")
TESTED_SOC = "V2.1.1"
# Firmware with a change list of its own, kept apart from edits.py: (versions, features, label). 1.6.0 is the
# Plus 4 before the QIDI Box (grease/edits_v160.py).
OWN_LISTS = ((edits_v160.FIRMWARE, edits_v160.FEATURES, edits_v160.LABEL),)


def own_list(soc_version):
    soc = normalize_soc(soc_version)
    for versions, features, label in OWN_LISTS:
        if soc in versions:
            return features, label
    return None, None


def features_for(soc_version):
    """The change list for this firmware: its own list if it has one, otherwise edits.py's."""
    features, _ = own_list(soc_version)
    return FEATURES if features is None else features


def supported_soc():
    return SUPPORTED_SOC + tuple(v for versions, _, _ in OWN_LISTS for v in versions)


class GreaseError(Exception):
    """A reason to stop before changing anything, or after putting everything back."""


class Paths(object):
    def __init__(self, home=None, model_file=MODEL_FILE):
        self.home = home or os.path.expanduser("~")
        self.config = os.path.join(self.home, "printer_data", "config")
        self.state_dir = os.path.join(self.home, ".plus4-grease")
        self.state = os.path.join(self.state_dir, "state.json")
        self.backups = os.path.join(self.state_dir, "backups")
        self.model_file = model_file

    def config_file(self, name):
        return os.path.join(self.config, name)

    def file(self, name):
        """A name from the edits: in the config folder, or ~/name in the home folder."""
        return os.path.join(self.home, name[2:]) if is_home(name) else self.config_file(name)


def is_home(name):
    return name.startswith("~/")


# ------------------------------------------------------------------ checks
def read_model(paths):
    try:
        with open(paths.model_file, "r") as handle:
            return handle.read().strip()
    except OSError:
        return None


def parse_soc_version(text):
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "soc":
            return normalize_soc(value)
    return None


def normalize_soc(value):
    """'V2.1.1' for 'V2.1.1', 'v2.1.1' or '2.1.1'; anything else as it was written."""
    value = (value or "").strip()
    match = re.match(r"^[Vv]?(\d+(?:\.\d+)+)$", value)
    return "V" + match.group(1) if match else (value or None)


def read_soc_version(runner=subprocess.run):
    """QIDI keeps the firmware version in /root, so it's read with sudo, which asks for the password."""
    try:
        done = runner(["sudo", "cat", VERSION_FILE], stdout=subprocess.PIPE, universal_newlines=True,
                      timeout=120)
    except Exception:  # noqa: BLE001 - reported as unknown
        return None
    if done.returncode != 0:
        return None
    return parse_soc_version(done.stdout)


def check_identity(paths):
    """Checks that need no sudo: run before asking for the password."""
    if os.geteuid() == 0:
        raise GreaseError("Run Plus4 Grease as the mks user, not as root or with sudo.")
    model = read_model(paths)
    if model != MODEL:
        raise GreaseError("This isn't a QIDI Plus 4 ({} says {!r}). Plus4 Grease only supports the Plus 4."
                          .format(paths.model_file, model))
    if not os.path.isdir(paths.config):
        raise GreaseError("No Klipper config folder at {}.".format(paths.config))


def check_printer(paths, soc_version, any_firmware=False):
    check_identity(paths)
    if normalize_soc(soc_version) not in supported_soc() and not any_firmware:
        raise GreaseError(
            "QIDI firmware {} isn't supported; Plus4 Grease is made for {}. Update the printer first. "
            "(--any-firmware skips this check; every change still applies only where QIDI's stock text "
            "is found.)".format(soc_version or "unknown", ", ".join(supported_soc())))


def firmware_note(soc_version):
    """A line to print on supported firmware Plus4 Grease hasn't been tested on; None otherwise."""
    soc = normalize_soc(soc_version)
    _, label = own_list(soc)
    if label:
        return ("QIDI firmware {}, from before the QIDI Box. Plus4 Grease uses its own {} change list here "
                "(grease/edits_v160.py), checked against QIDI's published {} files but not yet tested on a "
                "printer. The Box changes aren't offered.".format(soc, label, label))
    if soc in SUPPORTED_SOC and soc != TESTED_SOC:
        return ("QIDI firmware {}. Plus4 Grease is tested on {}; {} should work the same, and each change "
                "still applies only where QIDI's stock text is found.".format(soc, TESTED_SOC, soc))
    return None


# ------------------------------------------------------------------ edits
def occurrences(text, block):
    """Where block appears starting at the beginning of a line. A block found in the middle of a line
    (after a '#', say) doesn't count: that line is something else."""
    found, start = [], 0
    while True:
        index = text.find(block, start)
        if index < 0:
            return found
        if index == 0 or text[index - 1] == "\n":
            found.append(index)
        start = index + 1


def bare(text, edit):
    """Where the edit's stock block appears outside its replacement. An edit that inserts lines after a
    line has that line inside its replacement too, and that one doesn't count."""
    ours = [(start, start + len(edit.replace)) for start in occurrences(text, edit.replace)]
    return [i for i in occurrences(text, edit.find) if not any(a <= i < b for a, b in ours)]


def swap(text, old, new, index=None):
    """Replace a line-start occurrence of old (the one at index; by default the first) with new."""
    index = occurrences(text, old)[0] if index is None else index
    return text[:index] + new + text[index + len(old):]


def feature_status(text_by_file, feature):
    """'applied', 'available', 'update', or 'skipped' (the file isn't QIDI's stock text where it matters). A
    file the feature creates counts as applied when it's there with the feature's text, available when it's
    not there, update when it's an earlier Plus4 Grease version's (feature.replaces), and skipped when
    something else is there."""
    states = []
    older = {(name, digest) for name, digest in feature.replaces or ()}
    for name, content in feature.files or ():
        text = text_by_file.get(name)
        if text is None:
            states.append("available")
        elif text == content:
            states.append("applied")
        elif (name, hashlib.sha256(text.encode("utf-8")).hexdigest()) in older:
            states.append("update")
        else:
            return "skipped"
    for edit in feature.edits:
        text = text_by_file.get(edit.file)
        if text is None:
            return "skipped"
        stock, ours = len(bare(text, edit)), len(occurrences(text, edit.replace))
        if ours == 1 and stock == 0:
            states.append("applied")
        elif stock == 1 and ours == 0:
            states.append("available")
        else:
            return "skipped"
    if all(s == "applied" for s in states):
        return "applied"
    if all(s == "available" for s in states):
        return "available"
    if "update" in states and all(s in ("applied", "update") for s in states):
        return "update"
    return "skipped"


def apply_feature(text_by_file, feature):
    """Makes each edit still to be made (an update has its edits already) and writes the feature's files."""
    for edit in feature.edits:
        found = bare(text_by_file[edit.file], edit)
        if len(found) == 1:
            text_by_file[edit.file] = swap(text_by_file[edit.file], edit.find, edit.replace, found[0])
    for name, content in feature.files or ():
        text_by_file[name] = content


def revert_feature(text_by_file, feature):
    """None for a file the feature created: it's to be removed."""
    for edit in feature.edits:
        text_by_file[edit.file] = swap(text_by_file[edit.file], edit.replace, edit.find)
    for name, _ in feature.files or ():
        text_by_file[name] = None


def touched(features):
    return sorted({e.file for f in features for e in f.edits} | {n for f in features for n, _ in f.files or ()})


def own_setting_edit(text, setting):
    """For an option someone set by hand: (edit, note). The edit sets the option to the feature's value
    in its section, keeping the rest of the line; note says what's there now. (None, why) when it can't
    be done safely: the section isn't there exactly once, the option is set more than once in it, or it
    already has the value."""
    if "\r" in text:
        return None, "{} has Windows line endings".format(setting.file)
    lines = text.splitlines(True)
    header = re.compile(r"\[{}\][ \t]*(?:[#;].*)?\n".format(re.escape(setting.section)))
    starts = [i for i, line in enumerate(lines) if header.match(line)]
    if len(starts) != 1:
        return None, "[{}] is in {} {} times".format(setting.section, setting.file, len(starts))
    start = starts[0]
    end = start + 1
    while end < len(lines) and not lines[end].startswith("["):
        end += 1
    option = re.compile(r"{}[ \t]*[:=][ \t]*([^#;\s]*)".format(re.escape(setting.option)), re.I)
    found = [i for i in range(start + 1, end) if option.match(lines[i])]
    want = str(setting.value)
    if len(found) > 1:
        return None, "{}: is set {} times under [{}]".format(setting.option, len(found), setting.section)
    if not found:
        # The line after the header goes into the edit too, so the stock text isn't inside the new text.
        if start + 1 >= len(lines):
            return None, "[{}] is the last line of {}".format(setting.section, setting.file)
        note = "no {}: line under [{}] (Klipper then uses 50)".format(setting.option, setting.section)
        find = lines[start] + lines[start + 1]
        replace = lines[start] + "{}: {}\n".format(setting.option, want) + lines[start + 1]
    else:
        line = lines[found[0]]
        match = option.match(line)
        current = match.group(1)
        try:
            if float(current) == float(setting.value):
                return None, "already {}".format(want)
        except ValueError:
            pass
        note = "{} under [{}]".format(line.strip(), setting.section)
        find = "".join(lines[start:found[0] + 1])
        replace = "".join(lines[start:found[0]]) + line[:match.start(1)] + want + line[match.end(1):]
    if text.count(find) != 1 or text.count(replace) != 0 or find in replace:
        return None, "[{}] isn't laid out in a way that can be changed safely".format(setting.section)
    return Edit(setting.file, find, replace), note


def user_files(features):
    return [u for f in features for u in f.user_files or ()]


def read_files(paths, features=None):
    features = FEATURES if features is None else features
    texts = {}
    for name in touched(features) + [u.name for u in user_files(features)]:
        try:
            with open(paths.file(name), "r", encoding="utf-8", newline="") as handle:
                texts[name] = handle.read()
        except OSError:
            pass
    return texts


def write_file(path, text):
    """Write next to the file, flush it to storage, then swap it in, so a power cut leaves either the
    old file or the new one."""
    temp = path + ".plus4-grease.tmp"
    with open(temp, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    if os.path.exists(path):
        shutil.copymode(path, temp)
    else:
        os.chmod(temp, 0o644)
    os.replace(temp, path)
    directory = os.open(os.path.dirname(path), os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def backup_name(name):
    """Where a file goes in a backup folder: home files under home/."""
    return os.path.join("home", name[2:]) if is_home(name) else name


def backup(paths, names):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(paths.backups, stamp)
    os.makedirs(folder, exist_ok=True)
    for name in names:
        if os.path.exists(paths.file(name)):
            target = os.path.join(folder, backup_name(name))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(paths.file(name), target)
    return folder


def put(paths, name, text, runner=None):
    """Write a file, or remove it for None. Home files are root's (QIDI's Box templates): sudo writes
    them, keeping their owner and mode."""
    path = paths.file(name)
    if is_home(name):
        if text is None:
            system.remove_owned(path, runner)
        else:
            system.write_owned(path, text, paths.state_dir, runner)
    elif text is None:
        if os.path.exists(path):
            os.unlink(path)
    else:
        write_file(path, text)


def write_changes(paths, texts, names, runner=None, done=None):
    """Write each file; None removes it. done, if given, collects the names written so far."""
    for name in names:
        put(paths, name, texts.get(name), runner)
        if done is not None:
            done.append(name)


def restore(paths, folder, names, runner=None):
    """Put the backed-up files back; a file that wasn't there at backup time is removed."""
    for name in names:
        source = os.path.join(folder, backup_name(name))
        if os.path.isfile(source):
            with open(source, "r", encoding="utf-8", newline="") as handle:
                put(paths, name, handle.read(), runner)
        elif os.path.exists(paths.file(name)):
            put(paths, name, None, runner)


def load_state(paths):
    try:
        with open(paths.state, "r") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def save_state(paths, state):
    os.makedirs(paths.state_dir, exist_ok=True)
    with open(paths.state + ".tmp", "w") as handle:
        json.dump(state, handle, indent=1, sort_keys=True)
    os.replace(paths.state + ".tmp", paths.state)


# ------------------------------------------------------------------ actions
# feature: with the edits that apply on this printer. note: for a feature with a setting, what the
# printer has there. replaceable: --replace-own-speeds could set it. replacing: this run will.
Row = collections.namedtuple("Row", "feature status note replaceable replacing")


def effective(feature, state):
    """The feature with the edit an earlier --replace-own-speeds install made, if there was one."""
    own = state.get("own_values", {}).get(feature.id)
    if own:
        return feature._replace(edits=(Edit(own["file"], own["find"], own["replace"]),))
    return feature


def plan(paths, replace_own=False, options=(), features=None):
    """Rows for every feature of the list (edits.py's unless the firmware has its own). An opt-in
    feature that could apply but wasn't asked for is 'optional', unless another feature of the same switch
    is already installed (an update brings its new parts). A feature whose required one can't be applied
    is skipped."""
    features = FEATURES if features is None else features
    texts = read_files(paths, features)
    state = load_state(paths)
    found = {f.id: feature_status(texts, effective(f, state)) for f in features}
    options = set(options) | {f.option for f in features if f.option and found[f.id] in ("applied", "update")}
    rows, by_id = [], {}
    for feature in features:
        current = effective(feature, state)
        status_now = found[feature.id]
        if status_now == "available" and feature.option and feature.option not in options:
            status_now = "optional"
        needed = by_id.get(feature.requires)
        if needed is not None and needed.status == "skipped" and status_now in ("available", "optional"):
            rows.append(Row(current, "skipped", "needs: " + needed.feature.title, False, False))
            by_id[feature.id] = rows[-1]
            continue
        note, replaceable, replacing = "", False, False
        if status_now == "skipped" and feature.setting and feature.setting.file in texts:
            edit, note = own_setting_edit(texts[feature.setting.file], feature.setting)
            replaceable = edit is not None
            if replaceable and replace_own:
                current, status_now, replacing = feature._replace(edits=(edit,)), "available", True
        rows.append(Row(current, status_now, note, replaceable, replacing))
        by_id[feature.id] = rows[-1]
    return texts, rows


def check_commands(klipper, rows):
    """A feature that renames QIDI commands is skipped if the running Klipper lacks one of them: Klipper
    wouldn't start with it."""
    have, checked = None, []
    for row in rows:
        if row.feature.commands and row.status == "available":
            if have is None:
                have = klipper.commands() or set()
            missing = [c for c in row.feature.commands if c not in have]
            if missing:
                row = row._replace(status="skipped", note="missing: " + ", ".join(missing))
        checked.append(row)
    return checked


def skip_reason(row):
    if row.note.startswith("missing: "):
        return ("Klipper here has no {} to put the lock in front of (or couldn't be asked), so this is "
                "left out.".format(row.note[9:]))
    if row.note.startswith("needs: "):
        return "This works with \"{}\", which is left alone here, so this is too.".format(row.note[7:])
    setting = row.feature.setting
    if row.replaceable:
        return ("Your {} has {}. Add --replace-own-speeds to set it to {}; uninstall puts yours "
                "back.".format(setting.file, row.note, setting.value))
    if setting and row.note.startswith("already"):
        return "Your {} already has {}, so there's nothing to change.".format(setting.file, setting.value)
    return "QIDI's stock text isn't there, so this is left alone." + (" ({})".format(row.note) if row.note else "")


def check_loaded(klipper, features, report):
    """Klipper reads every included file, so a later file can set the same option again. Say so if
    what Klipper loaded isn't what was written."""
    features = [f for f in features if f.setting]
    if not features:
        return
    settings = klipper.settings()
    if settings is None:
        report("Couldn't read Klipper's settings to check the new values.")
        return
    for feature in features:
        s = feature.setting
        loaded = settings.get(s.section, {}).get(s.option)
        try:
            same = float(loaded) == float(s.value)
        except (TypeError, ValueError):
            same = False
        if same:
            report("  Klipper is using {} = {} under [{}].".format(s.option, s.value, s.section))
        else:
            report("  Note: Klipper is using {} = {} under [{}], not {}. Another config file sets it after {}; "
                   "change it there.".format(s.option, loaded, s.section, s.value, s.file))


def report_usb(usb, report):
    report("  {:9}  {}".format(usb, system.TITLE))
    if usb == "skipped":
        report("             Other files are where Plus4 Grease's would go ({}, {}), so this is left "
               "alone.".format(system.RULE, system.SCRIPT))


def mark_applied(paths, feature_id, on, firmware=None):
    state = load_state(paths)
    applied = set(state.get("applied", []))
    applied = applied | {feature_id} if on else applied - {feature_id}
    state["applied"], state["version"] = sorted(applied), VERSION
    if firmware:
        state["firmware"] = normalize_soc(firmware)
    save_state(paths, state)


def settle_user_files(texts, features, options):
    """{name: new text} for the user files of the features that will be applied, and notes to report."""
    changes, notes = {}, []
    for user in user_files(features):
        text, note = user.settle(texts.get(user.name), set(options))
        if text is not None:
            changes[user.name] = text
        if note:
            notes.append(note)
    return changes, notes


def write_all(paths, texts, names, folder, runner):
    """Write the changes; on a failure put back the files already written and stop."""
    done = []
    try:
        write_changes(paths, texts, names, runner, done)
    except OSError as error:
        try:
            restore(paths, folder, done, runner)
        except OSError as again:
            raise GreaseError("Writing the changes failed ({}) and so did putting the files back ({}). The "
                              "files from before are in {}.".format(error, again, folder))
        raise GreaseError("Writing the changes failed: {}. The files were put back, so nothing is "
                          "changed.".format(error))


def recorded_features(paths):
    """The change list the last install used, from the firmware it recorded; edits.py's if none."""
    return features_for(load_state(paths).get("firmware"))


def install(paths, klipper, report, dry_run=False, replace_own=False, runner=None, root=None, options=(),
            firmware=None):
    """firmware: the version read from the printer. It picks the change list and is recorded for status and
    uninstall."""
    features = features_for(firmware)
    texts, rows = plan(paths, replace_own, options, features)
    rows = check_commands(klipper, rows)
    todo = [row for row in rows if row.status in ("available", "update")]
    kept = [row.feature for row in rows if row.status in ("applied", "available", "update")]
    users, user_notes = settle_user_files(texts, kept, options)
    usb = system.status(paths, root)
    for row in rows:
        report("  {:9}  {}".format(row.status, row.feature.title))
        if row.replacing:
            report("             Replacing your {}; uninstall puts it back.".format(row.note))
        elif row.status == "optional":
            report("             Off unless you ask: add --{} to install it.".format(row.feature.option))
        elif row.status == "update":
            report("             An earlier Plus4 Grease version of this is installed; this updates it.")
        elif row.status == "skipped":
            report("             " + skip_reason(row))
    report_usb(usb, report)
    for note in user_notes:
        report(("Would do this: " if dry_run else "") + note)
    if not todo and not users and usb != "available":
        report("Nothing to change.")
        return 0
    if dry_run:
        report("Dry run: nothing was changed.")
        return 0
    if todo or users:
        klipper.require_idle()
    if usb == "available":
        try:
            system.install(paths, report, runner)
        except OSError as error:
            raise GreaseError("The USB event log couldn't be installed: {}. Nothing else was changed.".format(error))
        mark_applied(paths, "usb_event_log", True, firmware)
        if not todo and not users:
            report("Done. Applied: usb_event_log.")
            return 0
    klipper.require_idle()
    names = touched([row.feature for row in todo]) + sorted(users)
    folder = backup(paths, names)
    backed = [n for n in names if texts.get(n) is not None]
    if backed:
        report("Backed up {} to {}".format(", ".join(backed), folder))
    for row in todo:
        apply_feature(texts, row.feature)
    texts.update(users)
    write_all(paths, texts, names, folder, runner)
    state = load_state(paths)
    applied = sorted(set(state.get("applied", [])) | {row.feature.id for row in todo})
    own_values = dict(state.get("own_values", {}))
    for row in todo:
        if row.replacing:
            edit = row.feature.edits[0]
            own_values[row.feature.id] = {"file": edit.file, "find": edit.find, "replace": edit.replace,
                                          "was": row.note}
    new_state = {"version": VERSION, "applied": applied, "last_backup": folder,
                 "installed_at": datetime.datetime.now().isoformat(timespec="seconds")}
    if firmware:
        new_state["firmware"] = normalize_soc(firmware)
    if own_values:
        new_state["own_values"] = own_values
    save_state(paths, new_state)
    report("Restarting Klipper to load the changes...")
    if not klipper.restart_and_wait():
        report("Klipper didn't come back ready. Putting the files back...")
        restore(paths, folder, names, runner)
        if usb == "available":
            system.uninstall(paths, report, runner)
            state["applied"] = sorted(set(state.get("applied", [])) - {"usb_event_log"})
        save_state(paths, dict(state))
        klipper.restart_and_wait()
        raise GreaseError("Klipper didn't start with the changes, so they were taken out again. Nothing "
                          "is left changed. Please report this with ~/printer_data/logs/klippy.log.")
    check_loaded(klipper, [row.feature for row in todo], report)
    report("Done. Applied: {}.".format(", ".join(
        (["usb_event_log"] if usb == "available" else []) + [row.feature.id for row in todo]
        + sorted(users)) or "your settings"))
    return 0


def uninstall(paths, klipper, report, runner=None, root=None, firmware=None):
    """Uses the change list the install recorded, or firmware's (read from the printer) if none was."""
    state = load_state(paths)
    features = features_for(state.get("firmware") or firmware)
    texts, rows = plan(paths, features=features)
    todo = [row.feature for row in rows if row.status in ("applied", "update")]
    for row in rows:
        if row.status == "skipped" and row.feature.id in state.get("applied", []):
            report("  left alone  {} (changed since install)".format(row.feature.title))
    usb = system.status(paths, root)
    if usb == "applied":
        try:
            system.uninstall(paths, report, runner)
        except OSError as error:
            raise GreaseError("The USB event log couldn't be removed: {}.".format(error))
        report("  removed    {}".format(system.TITLE))
        mark_applied(paths, "usb_event_log", False)
        state = load_state(paths)
    elif usb == "skipped" and "usb_event_log" in state.get("applied", []):
        report("  left alone  {} (changed since install)".format(system.TITLE))
    if not todo:
        if usb != "applied":
            report("Nothing of Plus4 Grease is applied.")
        save_state(paths, {"version": VERSION, "applied": []})
        return 0
    klipper.require_idle()
    gone = []
    for user in user_files(todo):
        text = texts.get(user.name)
        if text is not None and text in user.defaults:
            gone.append(user.name)
        elif text is not None:
            report("  kept       {}: you've changed it. Delete it yourself if you don't want it.".format(user.name))
    names = touched(todo) + gone
    folder = backup(paths, names)
    own = state.get("own_values", {})
    for feature in todo:
        revert_feature(texts, feature)
        was = own.get(feature.id, {}).get("was")
        report("  removed    {}{}".format(feature.title, " (yours is back: {})".format(was) if was else ""))
    for name in gone:
        texts[name] = None
    write_all(paths, texts, names, folder, runner)
    save_state(paths, {"version": VERSION, "applied": [], "last_backup": folder})
    report("Restarting Klipper...")
    if not klipper.restart_and_wait():
        raise GreaseError("Klipper didn't come back ready after the uninstall. QIDI's stock text is back in "
                          "place; the files from before the uninstall are in {}.".format(folder))
    report("Done. QIDI's stock text is back.")
    return 0


def status(paths, report, root=None):
    """No sudo here, so the firmware isn't read: the list is the one the last install recorded."""
    state = load_state(paths)
    features = recorded_features(paths)
    _, label = own_list(state.get("firmware"))
    if label:
        report("  Firmware {} (recorded at install): Plus4 Grease's {} change list.".format(state["firmware"], label))
    texts, rows = plan(paths, features=features)
    for row in rows:
        note = ""
        if row.status == "available" and row.feature.id in state.get("applied", []):
            note = " (was applied; a QIDI update probably replaced the file, so install again)"
        elif row.status == "applied" and row.feature.id in state.get("own_values", {}):
            note = " (replacing your {})".format(state["own_values"][row.feature.id]["was"])
        elif row.status == "optional":
            note = "\n             Off unless you ask: install --{} adds it.".format(row.feature.option)
        elif row.status == "update":
            note = "\n             An earlier Plus4 Grease version of this is installed; install updates it."
        elif row.status == "skipped":
            note = "\n             " + skip_reason(row)
        if row.status in ("applied", "update"):
            for user in row.feature.user_files or ():
                if texts.get(user.name) is not None:
                    note += "\n             " + user.describe(texts[user.name])
        report("  {:9}  {}{}".format(row.status, row.feature.title, note))
    report_usb(system.status(paths, root), report)
    return 0
