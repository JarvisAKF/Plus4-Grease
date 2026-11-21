"""Install, uninstall, and status for Plus4 Grease. Python 3.7."""
import collections
import datetime
import json
import os
import re
import shutil
import subprocess

from . import VERSION
from .edits import FEATURES, Edit

MODEL_FILE = "/dev_info.txt"
MODEL = "QIDI@x-plus_4"
VERSION_FILE = "/root/xindi/version"
SUPPORTED_SOC = ("V2.1.1",)


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
            return value.strip()
    return None


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
    if soc_version not in SUPPORTED_SOC and not any_firmware:
        raise GreaseError(
            "QIDI firmware {} isn't supported; Plus4 Grease is made for {}. Update the printer first. "
            "(--any-firmware skips this check; every change still applies only where QIDI's stock text "
            "is found.)".format(soc_version or "unknown", ", ".join(SUPPORTED_SOC)))


# ------------------------------------------------------------------ edits
def feature_status(text_by_file, feature):
    """'applied', 'available', or 'skipped' (the file isn't QIDI's stock text where it matters)."""
    states = []
    for edit in feature.edits:
        text = text_by_file.get(edit.file)
        if text is None:
            return "skipped"
        stock, ours = text.count(edit.find), text.count(edit.replace)
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
    return "skipped"


def apply_feature(text_by_file, feature):
    for edit in feature.edits:
        text_by_file[edit.file] = text_by_file[edit.file].replace(edit.find, edit.replace, 1)


def revert_feature(text_by_file, feature):
    for edit in feature.edits:
        text_by_file[edit.file] = text_by_file[edit.file].replace(edit.replace, edit.find, 1)


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
    for name in sorted({e.file for f in FEATURES for e in f.edits}):
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
    shutil.copymode(path, temp)
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
        shutil.copy2(paths.config_file(name), os.path.join(folder, name))
    return folder


def restore(paths, folder, names):
    for name in names:
        source = os.path.join(folder, name)
        if os.path.isfile(source):
            with open(source, "r", encoding="utf-8", newline="") as handle:
                write_file(paths.config_file(name), handle.read())


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


def plan(paths, replace_own=False):
    texts = read_files(paths)
    state = load_state(paths)
    rows = []
    for feature in FEATURES:
        current = effective(feature, state)
        status_now = feature_status(texts, current)
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


def install(paths, klipper, report, dry_run=False, replace_own=False):
    texts, rows = plan(paths, replace_own)
    todo = [row for row in rows if row.status == "available"]
    for row in rows:
        report("  {:9}  {}".format(row.status, row.feature.title))
        if row.replacing:
            report("             Replacing your {}; uninstall puts it back.".format(row.note))
        elif row.status == "skipped":
            report("             " + skip_reason(row))
    if not todo:
        report("Nothing to change.")
        return 0
    if dry_run:
        report("Dry run: nothing was changed.")
        return 0
    klipper.require_idle()
    names = sorted({e.file for row in todo for e in row.feature.edits})
    folder = backup(paths, names)
    report("Backed up {} to {}".format(", ".join(names), folder))
    for row in todo:
        apply_feature(texts, row.feature)
    for name in names:
        write_file(paths.config_file(name), texts[name])
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
        save_state(paths, dict(state))
        klipper.restart_and_wait()
        raise GreaseError("Klipper didn't start with the changes, so they were taken out again. Nothing "
                          "is left changed. Please report this with ~/printer_data/logs/klippy.log.")
    check_loaded(klipper, [row.feature for row in todo], report)
    report("Done. Applied: {}.".format(", ".join(row.feature.id for row in todo)))
    return 0


def uninstall(paths, klipper, report):
    texts, rows = plan(paths)
    state = load_state(paths)
    todo = [row.feature for row in rows if row.status == "applied"]
    for row in rows:
        if row.status == "skipped" and row.feature.id in state.get("applied", []):
            report("  left alone  {} (changed since install)".format(row.feature.title))
    if not todo:
        report("Nothing of Plus4 Grease is applied.")
        save_state(paths, {"version": VERSION, "applied": []})
        return 0
    klipper.require_idle()
    names = sorted({e.file for f in todo for e in f.edits})
    folder = backup(paths, names)
    own = state.get("own_values", {})
    for feature in todo:
        revert_feature(texts, feature)
        was = own.get(feature.id, {}).get("was")
        report("  removed    {}{}".format(feature.title, " (yours is back: {})".format(was) if was else ""))
    for name in names:
        write_file(paths.config_file(name), texts[name])
    save_state(paths, {"version": VERSION, "applied": [], "last_backup": folder})
    report("Restarting Klipper...")
    if not klipper.restart_and_wait():
        raise GreaseError("Klipper didn't come back ready after the uninstall. QIDI's stock text is back in "
                          "place; the files from before the uninstall are in {}.".format(folder))
    report("Done. QIDI's stock text is back.")
    return 0


def status(paths, report):
    _, rows = plan(paths)
    state = load_state(paths)
    for row in rows:
        note = ""
        if row.status == "available" and row.feature.id in state.get("applied", []):
            note = " (was applied; a QIDI update probably replaced the file, so install again)"
        elif row.status == "applied" and row.feature.id in state.get("own_values", {}):
            note = " (replacing your {})".format(state["own_values"][row.feature.id]["was"])
        elif row.status == "skipped":
            note = "\n             " + skip_reason(row)
        report("  {:9}  {}{}".format(row.status, row.feature.title, note))
    return 0
