"""Install, uninstall, and status for Plus4 Grease. Python 3.7."""
import collections
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess

from . import VERSION, system
from .edits import FEATURES, Edit

MODEL_FILE = "/dev_info.txt"
MODEL = "QIDI@x-plus_4"
VERSION_FILE = "/root/xindi/version"
# V2.1.1 is what Plus4 Grease is tested on. QIDI shipped 1.8.1 and 1.8.2 only as online updates, so their stock
# files can't be checked; QIDI's published 1.7.1 configs before them and V2.1.1's after them have the same text
# where every edit applies (docs/plus4-notes.md, "Firmware 1.8.x").
SUPPORTED_SOC = ("V2.1.1", "V1.8.2", "V1.8.1")
TESTED_SOC = "V2.1.1"


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
    if normalize_soc(soc_version) not in SUPPORTED_SOC and not any_firmware:
        raise GreaseError(
            "QIDI firmware {} isn't supported; Plus4 Grease is made for {}. Update the printer first. "
            "(--any-firmware skips this check; every change still applies only where QIDI's stock text "
            "is found.)".format(soc_version or "unknown", ", ".join(SUPPORTED_SOC)))


def firmware_note(soc_version):
    """A line to print on supported firmware Plus4 Grease hasn't been tested on; None otherwise."""
    soc = normalize_soc(soc_version)
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


def swap(text, old, new):
    """Replace the one line-start occurrence of old with new."""
    index = occurrences(text, old)[0]
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
        stock, ours = len(occurrences(text, edit.find)), len(occurrences(text, edit.replace))
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
        if len(occurrences(text_by_file[edit.file], edit.find)) == 1:
            text_by_file[edit.file] = swap(text_by_file[edit.file], edit.find, edit.replace)
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


def read_files(paths):
    texts = {}
    for name in touched(FEATURES):
        try:
            with open(paths.config_file(name), "r", encoding="utf-8", newline="") as handle:
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


def backup(paths, names):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(paths.backups, stamp)
    os.makedirs(folder, exist_ok=True)
    for name in names:
        if os.path.exists(paths.config_file(name)):
            shutil.copy2(paths.config_file(name), os.path.join(folder, name))
    return folder


def write_changes(paths, texts, names):
    """Write each file; None removes it."""
    for name in names:
        path = paths.config_file(name)
        if texts.get(name) is None:
            if os.path.exists(path):
                os.unlink(path)
        else:
            write_file(path, texts[name])


def restore(paths, folder, names):
    """Put the backed-up files back; a file that wasn't there at backup time is removed."""
    for name in names:
        source = os.path.join(folder, name)
        if os.path.isfile(source):
            with open(source, "r", encoding="utf-8", newline="") as handle:
                write_file(paths.config_file(name), handle.read())
        elif os.path.exists(paths.config_file(name)):
            os.unlink(paths.config_file(name))


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


def plan(paths, replace_own=False, options=()):
    """Rows for every feature. An opt-in feature that could apply but wasn't asked for is 'optional'."""
    texts = read_files(paths)
    state = load_state(paths)
    rows = []
    for feature in FEATURES:
        current = effective(feature, state)
        status_now = feature_status(texts, current)
        if status_now == "available" and feature.option and feature.option not in options:
            status_now = "optional"
        note, replaceable, replacing = "", False, False
        if status_now == "skipped" and feature.setting and feature.setting.file in texts:
            edit, note = own_setting_edit(texts[feature.setting.file], feature.setting)
            replaceable = edit is not None
            if replaceable and replace_own:
                current, status_now, replacing = feature._replace(edits=(edit,)), "available", True
        rows.append(Row(current, status_now, note, replaceable, replacing))
    return texts, rows


def skip_reason(row):
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


def mark_applied(paths, feature_id, on):
    state = load_state(paths)
    applied = set(state.get("applied", []))
    applied = applied | {feature_id} if on else applied - {feature_id}
    state["applied"], state["version"] = sorted(applied), VERSION
    save_state(paths, state)


def install(paths, klipper, report, dry_run=False, replace_own=False, runner=None, root=None, options=()):
    texts, rows = plan(paths, replace_own, options)
    todo = [row for row in rows if row.status in ("available", "update")]
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
    if not todo and usb != "available":
        report("Nothing to change.")
        return 0
    if dry_run:
        report("Dry run: nothing was changed.")
        return 0
    if todo:
        klipper.require_idle()
    if usb == "available":
        try:
            system.install(paths, report, runner)
        except OSError as error:
            raise GreaseError("The USB event log couldn't be installed: {}. Nothing else was changed.".format(error))
        mark_applied(paths, "usb_event_log", True)
        if not todo:
            report("Done. Applied: usb_event_log.")
            return 0
    klipper.require_idle()
    names = touched([row.feature for row in todo])
    folder = backup(paths, names)
    report("Backed up {} to {}".format(", ".join(n for n in names if texts.get(n) is not None), folder))
    for row in todo:
        apply_feature(texts, row.feature)
    write_changes(paths, texts, names)
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
    if own_values:
        new_state["own_values"] = own_values
    save_state(paths, new_state)
    report("Restarting Klipper to load the changes...")
    if not klipper.restart_and_wait():
        report("Klipper didn't come back ready. Putting the files back...")
        restore(paths, folder, names)
        if usb == "available":
            system.uninstall(paths, report, runner)
            state["applied"] = sorted(set(state.get("applied", [])) - {"usb_event_log"})
        save_state(paths, dict(state))
        klipper.restart_and_wait()
        raise GreaseError("Klipper didn't start with the changes, so they were taken out again. Nothing "
                          "is left changed. Please report this with ~/printer_data/logs/klippy.log.")
    check_loaded(klipper, [row.feature for row in todo], report)
    report("Done. Applied: {}.".format(", ".join(
        (["usb_event_log"] if usb == "available" else []) + [row.feature.id for row in todo])))
    return 0


def uninstall(paths, klipper, report, runner=None, root=None):
    texts, rows = plan(paths)
    state = load_state(paths)
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
    names = touched(todo)
    folder = backup(paths, names)
    own = state.get("own_values", {})
    for feature in todo:
        revert_feature(texts, feature)
        was = own.get(feature.id, {}).get("was")
        report("  removed    {}{}".format(feature.title, " (yours is back: {})".format(was) if was else ""))
    write_changes(paths, texts, names)
    save_state(paths, {"version": VERSION, "applied": [], "last_backup": folder})
    report("Restarting Klipper...")
    if not klipper.restart_and_wait():
        raise GreaseError("Klipper didn't come back ready after the uninstall. QIDI's stock text is back in "
                          "place; the files from before the uninstall are in {}.".format(folder))
    report("Done. QIDI's stock text is back.")
    return 0


def status(paths, report, root=None):
    _, rows = plan(paths)
    state = load_state(paths)
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
        report("  {:9}  {}{}".format(row.status, row.feature.title, note))
    report_usb(system.status(paths, root), report)
    return 0
