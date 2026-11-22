#!/usr/bin/env python3
"""Compare a QIDI Plus 4's Klipper config with QIDI's stock V2.1.1 config, section by section.

Run on the printer as mks:

    python3 ~/plus4-grease/tools/config_diff.py

It reads ~/printer_data/config and the stock files in ~/plus4-grease/stock/plus4-2.1.1 (from QIDI's V2.1.1
update package, QD_Plus4_SOC) and lists, file by file, the sections and options you added, removed, or
changed, with the stock and your values side by side, and macro bodies as a line diff. Plus4 Grease's own
edits are taken out first and listed on their own, so the rest is what was changed by hand or by another
mod (a Beacon conversion, say). The SAVE_CONFIG block at the end of printer.cfg is compared by section.
Serial numbers in USB paths and CAN UUIDs are hidden.

It changes nothing. The full result is also written to ~/plus4-grease-config-diff-<date>.txt.

This file runs on the printer's Python 3.7, so it uses 3.7 syntax and library features only.
"""
import collections
import difflib
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.join(HERE, "..", "stock", "plus4-2.1.1")
CONFIG = os.path.expanduser("~/printer_data/config")
COMPARED = ("printer.cfg", "gcode_macro.cfg", "box1.cfg", "box2.cfg", "box3.cfg", "box4.cfg", "moonraker.conf",
            "officiall_filas_list.cfg")
AUTOSAVE = "#*# <---------------------- SAVE_CONFIG ---------------------->"
SERIAL_IN_PATH = re.compile(r"(usb-[^\s'\"/]*?_)([0-9A-Fa-f]{8,})(-if\d+)")
UUID = re.compile(r"(canbus_uuid\s*[:=]\s*)([0-9A-Fa-f]{6,})")
OPTION = re.compile(r"^([^:=\s][^:=]*?)\s*[:=]\s*(.*)$")
# Copies people and Klipper leave next to the real files: printer-<date>.cfg (SAVE_CONFIG), printer1.cfg,
# printer_stock.cfg, gcode_macro_<date>.cfg, *.bak, dot files.
BACKUP = re.compile(r"(^printer[-_0-9].*\.cfg$|^printer_stock\.cfg$|_\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d\.cfg$|"
                    r"\.(bak|bkp|backup|old)$|^\.)")


def redact(text):
    return UUID.sub(r"\1<uuid>", SERIAL_IN_PATH.sub(r"\1<serial>\3", text))


def strip_comment(line):
    """Klipper drops whole-line comments and '#' or ';' comments that follow a space."""
    if line.lstrip().startswith(("#", ";")):
        return ""
    return re.split(r"\s[#;]", line, 1)[0].rstrip()


def parse(text):
    """(sections, autosave): each an ordered {section: {option: value}}; a multi-line value is a list of its
    lines. A section given twice is merged, later options winning, as Klipper does."""
    main, _, saved = text.partition(AUTOSAVE)
    sections = collections.OrderedDict()
    section = key = None
    for raw in main.splitlines():
        line = strip_comment(raw)
        if not line.strip():
            continue
        if line[0] in " \t":
            if section is not None and key is not None:
                value = sections[section][key]
                if not isinstance(value, list):
                    value = [value] if value else []
                value.append(line.strip())
                sections[section][key] = value
            continue
        if line.startswith("["):
            section = re.sub(r"\s+", " ", line.strip()[1:-1].strip())
            sections.setdefault(section, collections.OrderedDict())
            key = None
            continue
        match = OPTION.match(line)
        if match and section is not None:
            key = match.group(1).strip().lower()
            sections[section][key] = match.group(2).strip()
    autosave = collections.OrderedDict()
    if saved:
        body = "\n".join(line[4:] if line.startswith("#*# ") else line.lstrip("#*")
                         for line in saved.splitlines() if line.startswith("#*#"))
        autosave = parse(body)[0]
    return sections, autosave


def norm(value):
    if isinstance(value, list):
        return [re.sub(r"\s+", " ", v) for v in value if v]
    value = re.sub(r"\s*,\s*", ",", re.sub(r"\s+", " ", value.strip()))
    try:
        return float(value)
    except ValueError:
        return value


def show(value, limit=240):
    if isinstance(value, list):
        return "{} line{}".format(len(value), "" if len(value) == 1 else "s")
    value = redact(value)
    return value if len(value) <= limit else value[:limit - 3] + "..."


def compare(stock, yours, out, label="", body_diff=True, saved=None):
    """Section-by-section differences between two parsed configs. Returns the number of differences.
    saved: your SAVE_CONFIG block; an option gone from a section but set there was moved by SAVE_CONFIG
    (Klipper comments out the line it overrides), so it's shown as moved, with both values."""
    count = 0
    added = [s for s in yours if s not in stock]
    removed = [s for s in stock if s not in yours]
    if added:
        out("  {}Sections you added:".format(label))
        for name in added:
            count += 1
            out("    [{}]".format(redact(name)))
            for key, value in yours[name].items():
                out("        {}: {}".format(key, show(value)))
    if removed:
        out("  {}Sections in QIDI's stock config that you don't have:".format(label))
        for name in removed:
            count += 1
            out("    [{}]".format(name))
    for name in stock:
        if name not in yours:
            continue
        a, b = stock[name], yours[name]
        lines = []
        for key in a:
            if key not in b and saved and key in saved.get(name, {}):
                new = saved[name][key]
                lines.append("        {}: {} -> {} (now in the SAVE_CONFIG block{})".format(
                    key, show(a[key]), show(new), "" if norm(a[key]) != norm(new) else ", same value"))
            elif key not in b:
                lines.append("        removed {}: {}".format(key, show(a[key])))
            elif norm(a[key]) != norm(b[key]):
                if isinstance(a[key], list) or isinstance(b[key], list):
                    old = a[key] if isinstance(a[key], list) else [a[key]]
                    new = b[key] if isinstance(b[key], list) else [b[key]]
                    lines.append("        {}: changed ({} lines in stock, {} in yours)".format(
                        key, len(old), len(new)))
                    if body_diff:
                        diff = list(difflib.unified_diff(old, new, lineterm="", n=1))[2:]
                        lines.extend("          " + redact(d)[:150] for d in diff)
                else:
                    lines.append("        {}: {} -> {}".format(key, show(a[key]), show(b[key])))
        for key in b:
            if key not in a:
                lines.append("        added {}: {}".format(key, show(b[key])))
        if lines:
            count += 1
            out("  {}Changed: [{}]".format(label, redact(name)))
            for line in lines:
                out(line)
    return count


def undo_grease(texts, config):
    """Take Plus4 Grease's applied edits out of the files, so they don't count as hand changes.
    Returns (texts, titles of what was taken out)."""
    sys.path.insert(0, os.path.join(HERE, ".."))
    try:
        from grease import core
    except Exception:  # noqa: BLE001 - run without Plus4 Grease installed
        return texts, []
    home = os.path.dirname(os.path.dirname(os.path.abspath(config)))  # <home>/printer_data/config
    state = core.load_state(core.Paths(home=home))
    taken = []
    texts = dict(texts)
    for feature in core.FEATURES:
        current = core.effective(feature, state)
        if all(edit.file in texts for edit in current.edits) and core.feature_status(texts, current) == "applied":
            core.revert_feature(texts, current)
            taken.append(current.title)
    return texts, taken


def read(path):
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as handle:
        return handle.read()


def main(argv=None):
    stock_dir, config = os.path.abspath(STOCK), CONFIG
    if argv:
        config = argv[0]
    if not os.path.isdir(stock_dir):
        print("QIDI's stock files aren't at {}; copy the stock folder from Plus4 Grease there.".format(stock_dir))
        return 1
    lines = []

    def out(line=""):
        lines.append(line)
        print(line)

    out("Your config ({}) against QIDI's stock V2.1.1 config ({}).".format(config, stock_dir))
    out("Serial numbers are hidden. Values are shown as stock -> yours.")
    yours = {}
    for name in COMPARED:
        path = os.path.join(config, name)
        if os.path.isfile(path):
            yours[name] = read(path)
    yours, taken = undo_grease(yours, config)
    out("")
    if taken:
        out("Plus4 Grease changes taken out before comparing (they're its own, listed by its status command):")
        for title in taken:
            out("  " + title)
        out("")

    total = 0
    for name in COMPARED:
        stock_path = os.path.join(stock_dir, name)
        if not os.path.isfile(stock_path):
            continue
        if name not in yours:
            out("{}: not in your config folder.".format(name))
            out("")
            continue
        if name.endswith(".cfg") or name.endswith(".conf"):
            stock_sections, stock_saved = parse(read(stock_path))
            your_sections, your_saved = parse(yours[name])
            out("{}:".format(name))
            count = compare(stock_sections, your_sections, out, saved=your_saved)
            if stock_saved or your_saved:
                saved = compare(stock_saved, your_saved, out, label="SAVE_CONFIG block: ", body_diff=False)
                count += saved
            if not count:
                out("  same as stock.")
            total += count
            out("")

    stock_names = set(os.listdir(stock_dir))
    others, backups = [], 0
    for name in sorted(os.listdir(config)):
        path = os.path.join(config, name)
        if name in stock_names or not (name.endswith(".cfg") or name.endswith(".conf")):
            continue
        if BACKUP.search(name):
            backups += 1
            continue
        if os.path.isfile(path):
            others.append(name)
    stock_includes = [s[len("include "):] for s in parse(read(os.path.join(stock_dir, "printer.cfg")))[0]
                      if s.startswith("include ")]
    your_includes = [s[len("include "):] for s in parse(yours.get("printer.cfg", ""))[0] if s.startswith("include ")]
    if others:
        out("Other config files (not in QIDI's update package, so not compared):")
        for name in others:
            notes = []
            if name in your_includes:
                notes.append("printer.cfg includes it")
            if name in stock_includes:
                notes.append("QIDI's printer.cfg includes it too")
            out("  {}{}".format(name, " ({})".format("; ".join(notes)) if notes else ""))
    if backups:
        out("  ...and {} backup cop{} (printer-<date>.cfg and the like), left out.".format(
            backups, "y" if backups == 1 else "ies"))
    out("")
    out("{} difference{} in all.".format(total, "" if total == 1 else "s"))
    report = os.path.expanduser("~/plus4-grease-config-diff-{}.txt".format(time.strftime("%Y%m%d-%H%M%S")))
    try:
        with open(report, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        print("Saved to {}".format(report))
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
