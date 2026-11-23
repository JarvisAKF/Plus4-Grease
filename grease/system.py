"""Plus4 Grease's one system-level piece: a USB event log. Python 3.7.

The Plus 4 keeps Linux's logs in RAM (Armbian's ramlog) and copies them to the eMMC only on a clean
shutdown, so switching the printer off loses them, and with them any record of a board disconnecting.
This installs a udev rule that runs a small script each time a USB device connects or disconnects. The
script adds one line to plus4-grease-usb.log in Klipper's log folder, on the eMMC, and flushes it to
storage. tools/klipper_report.py then lists the USB events around each Klipper shutdown, so "Lost
communication with MCU 'mcu_box1'" can be told apart from the Box being switched off or unplugged.

A line is: UTC time, Unix time, add or remove, the kernel's name for the USB port path (2-1.2.1.2), the
vendor/product/version IDs, and on add the device's manufacturer and product names. Serial numbers are
never written. The log keeps its last 2000 lines.

The files go where only root can change them (/etc/udev/rules.d and /usr/local/lib), since udev runs the
script as root.
"""
import os
import subprocess
import tempfile

# Tests point ROOT at a scratch folder and RUNNER at a fake sudo, so they never touch the real system.
ROOT = "/"
RUNNER = subprocess.run
RULE = "/etc/udev/rules.d/99-plus4-grease-usb.rules"
SCRIPT = "/usr/local/lib/plus4-grease/usb-event"
LOG_NAME = "plus4-grease-usb.log"
TITLE = "USB event log: a line in plus4-grease-usb.log each time a board connects or disconnects"


def log_path(paths):
    return os.path.join(paths.home, "printer_data", "logs", LOG_NAME)


def rule_text():
    return (
        "# Plus4 Grease: log each USB device connecting and disconnecting ({}).\n"
        "# Remove with: bash ~/plus4-grease/install.sh uninstall\n"
        "ACTION==\"add|remove\", SUBSYSTEM==\"usb\", ENV{{DEVTYPE}}==\"usb_device\", "
        "RUN+=\"{} $env{{ACTION}} %k $env{{PRODUCT}} '$attr{{manufacturer}}' '$attr{{product}}'\"\n"
    ).format(SCRIPT, SCRIPT)


def script_text(paths):
    return """#!/bin/sh
# Plus4 Grease USB event log, run by udev ({rule}) as root.
# Adds one line per USB device connecting or disconnecting to {log}.
# Arguments: action, kernel name, vendor/product/version, manufacturer, product. No serial numbers.
PATH=/usr/sbin:/usr/bin:/sbin:/bin
LOG='{log}'
[ -d "$(dirname "$LOG")" ] || exit 0
ACTION=${{1:--}}
KERNEL=${{2:--}}
IDS=${{3:--}}
[ $# -ge 3 ] && shift 3 || shift $#
NAME=$(printf '%s' "$*" | tr -cd '[:print:]' | sed 's/^ *//; s/ *$//' | cut -c1-80)
STAMP=$(date -u '+%Y-%m-%dT%H:%M:%S.%3NZ %s.%3N')
printf '%s %s %s %s %s\\n' "$STAMP" "$ACTION" "$KERNEL" "$IDS" "${{NAME:--}}" >> "$LOG" 2>/dev/null
chmod 0644 "$LOG" 2>/dev/null
if [ "$(stat -c %s "$LOG" 2>/dev/null || echo 0)" -gt 262144 ]; then
    tail -n 2000 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
fi
sync "$LOG" 2>/dev/null
exit 0
""".format(rule=RULE, log=log_path(paths))


def wanted(paths):
    return {RULE: rule_text(), SCRIPT: script_text(paths)}


def status(paths, root=None):
    """'applied' when both files are there with Plus4 Grease's text, 'available' when neither is,
    'skipped' when something else is in their place."""
    states = []
    for path, text in wanted(paths).items():
        where = os.path.join(root or ROOT, path.lstrip("/"))
        try:
            with open(where, "r", encoding="utf-8", newline="") as handle:
                states.append("applied" if handle.read() == text else "skipped")
        except FileNotFoundError:
            states.append("available")
        except OSError:
            states.append("skipped")
    if all(s == "applied" for s in states):
        return "applied"
    if all(s == "available" for s in states):
        return "available"
    return "skipped"


def _sudo(runner, *command):
    done = (runner or RUNNER)(["sudo"] + list(command), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                  universal_newlines=True, timeout=120)
    return done.returncode == 0, (done.stdout or "").strip()


def write_owned(path, text, scratch, runner=None):
    """Write a file only root can change (QIDI's Box templates), keeping its owner and mode."""
    try:
        info = os.stat(path)
        mode, owner, group = "{:04o}".format(info.st_mode & 0o7777), str(info.st_uid), str(info.st_gid)
    except FileNotFoundError:
        mode, owner, group = "0644", "root", "root"
    os.makedirs(scratch, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=scratch)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as out:
            out.write(text)
        ok, output = _sudo(runner, "install", "-m", mode, "-o", owner, "-g", group, temp, path)
    finally:
        os.unlink(temp)
    if not ok:
        raise OSError("couldn't write {}: {}".format(path, output))


def remove_owned(path, runner=None):
    ok, output = _sudo(runner, "rm", "-f", path)
    if not ok:
        raise OSError("couldn't remove {}: {}".format(path, output))


def install(paths, report, runner=None):
    """Copies the script and the rule into place with sudo, reloads udev, and writes a first line."""
    os.makedirs(paths.state_dir, exist_ok=True)
    for path, mode in ((SCRIPT, "0755"), (RULE, "0644")):
        handle, temp = tempfile.mkstemp(dir=paths.state_dir)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="") as out:
                out.write(wanted(paths)[path])
            ok, output = _sudo(runner, "install", "-D", "-m", mode, "-o", "root", "-g", "root", temp, path)
        finally:
            os.unlink(temp)
        if not ok:
            raise OSError("couldn't write {}: {}".format(path, output))
    ok, output = _sudo(runner, "udevadm", "control", "--reload-rules")
    if not ok:
        raise OSError("udev didn't reload its rules: {}".format(output))
    _sudo(runner, SCRIPT, "start", "-", "-", "Plus4", "Grease", "USB", "log", "installed")
    report("             USB events now go to {}.".format(log_path(paths)))


def uninstall(paths, report, runner=None):
    for path in (RULE, SCRIPT):
        ok, output = _sudo(runner, "rm", "-f", path)
        if not ok:
            raise OSError("couldn't remove {}: {}".format(path, output))
    _sudo(runner, "rmdir", os.path.dirname(SCRIPT))
    _sudo(runner, "udevadm", "control", "--reload-rules")
    report("             The log itself is left at {}.".format(log_path(paths)))
