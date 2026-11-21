"""Install, uninstall, and status for Plus4 Grease. Python 3.7."""
import datetime
import json
import os
import shutil
import subprocess

from . import VERSION
from .edits import FEATURES

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
def plan(paths):
    texts = read_files(paths)
    return texts, [(feature, feature_status(texts, feature)) for feature in FEATURES]


def install(paths, klipper, report, dry_run=False):
    texts, statuses = plan(paths)
    todo = [feature for feature, status in statuses if status == "available"]
    for feature, status in statuses:
        report("  {:9}  {}".format(status, feature.title))
        if status == "skipped":
            report("             QIDI's stock text isn't there, so this is left alone.")
    if not todo:
        report("Nothing to change.")
        return 0
    if dry_run:
        report("Dry run: nothing was changed.")
        return 0
    klipper.require_idle()
    names = sorted({e.file for f in todo for e in f.edits})
    folder = backup(paths, names)
    report("Backed up {} to {}".format(", ".join(names), folder))
    for feature in todo:
        apply_feature(texts, feature)
    for name in names:
        write_file(paths.config_file(name), texts[name])
    state = load_state(paths)
    applied = sorted(set(state.get("applied", [])) | {f.id for f in todo})
    save_state(paths, {"version": VERSION, "applied": applied, "last_backup": folder,
                       "installed_at": datetime.datetime.now().isoformat(timespec="seconds")})
    report("Restarting Klipper to load the changes...")
    if not klipper.restart_and_wait():
        report("Klipper didn't come back ready. Putting the files back...")
        restore(paths, folder, names)
        save_state(paths, dict(state))
        klipper.restart_and_wait()
        raise GreaseError("Klipper didn't start with the changes, so they were taken out again. Nothing "
                          "is left changed. Please report this with ~/printer_data/logs/klippy.log.")
    report("Done. Applied: {}.".format(", ".join(f.id for f in todo)))
    return 0


def uninstall(paths, klipper, report):
    texts, statuses = plan(paths)
    todo = [feature for feature, status in statuses if status == "applied"]
    for feature, status in statuses:
        if status == "skipped" and feature.id in load_state(paths).get("applied", []):
            report("  left alone  {} (changed since install)".format(feature.title))
    if not todo:
        report("Nothing of Plus4 Grease is applied.")
        save_state(paths, {"version": VERSION, "applied": []})
        return 0
    klipper.require_idle()
    names = sorted({e.file for f in todo for e in f.edits})
    folder = backup(paths, names)
    for feature in todo:
        revert_feature(texts, feature)
        report("  removed    {}".format(feature.title))
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
    _, statuses = plan(paths)
    state = load_state(paths)
    for feature, current in statuses:
        note = ""
        if current == "available" and feature.id in state.get("applied", []):
            note = " (was applied; a QIDI update probably replaced the file, so install again)"
        report("  {:9}  {}{}".format(current, feature.title, note))
    return 0
