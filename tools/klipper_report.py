#!/usr/bin/env python3
"""Klipper report for the QIDI Plus 4: how loaded the boards and the Pi were, and why Klipper stopped.

Run on the printer as mks:

    python3 ~/plus4-grease/tools/klipper_report.py          # klippy.log
    python3 ~/plus4-grease/tools/klipper_report.py --all    # klippy.log and the older days next to it

It only reads klippy.log. While the printer is busy or hot, Klipper writes a Stats line every second with
each board's load and link counters and the Pi's load and memory. This reads those lines and reports:

- the boards, the chip on each, and which motors each one drives at how many microsteps;
- for the last print: how busy each board was, how much of its serial link it used, link errors, and how
  hard the Pi worked, including any time Klipper's main loop stopped;
- for each time Klipper shut down ("Timer too close", "Lost communication", ...): what the numbers in the
  half minute before it point to. Klipper's own advice for "Timer too close" names every possible cause at
  once; the numbers usually rule most of them out.

The figures are the ones Klipper's scripts/graphstats.py plots: a board's busy share is mcu_awake over
the 5 s it covers, its task load is mcu_task_avg + 3 * mcu_task_stddev against 2.5 ms.

This file runs on the printer's Python 3.7, so it uses 3.7 syntax and library features only.
"""
import argparse
import collections
import glob
import os
import re
import sys
import time

LOG = "~/printer_data/logs/klippy.log"
USB_LOG = "plus4-grease-usb.log"   # Plus4 Grease's USB event log, next to klippy.log
USB_BEFORE, USB_AFTER = 60.0, 10.0  # seconds around a shutdown to show USB events from
STATS_INTERVAL = 5.0      # a board sends its load figures every 5 s
TASK_MAX = 0.0025         # graphstats.py's full scale for a board's task time
LOOKBACK = 30.0           # seconds of Stats read before a shutdown
CORES = 4                 # the Plus 4's RK3328
MCU_KEYS = {"mcu_awake", "mcu_task_avg", "mcu_task_stddev", "bytes_write", "bytes_read", "bytes_retransmit",
            "bytes_invalid", "send_seq", "receive_seq", "retransmit_seq", "srtt", "rttvar", "rto",
            "ready_bytes", "upcoming_bytes", "stalled_bytes", "freq", "adj"}
GLOBAL_KEYS = {"print_time", "buffer_time", "print_stall", "sysload", "cputime", "memavail", "sd_pos",
               "gcodein"}

START = re.compile(r"Start printer at (.*) \(([\d.]+) ([\d.]+)\)")
STATS = re.compile(r"Stats ([\d.]+): (.*)")
SHUTDOWN = re.compile(r"Transition to shutdown state: (.*)")
MCU_CONFIG = re.compile(r"MCU '([^']+)' config: (.*)")
TIMEOUT = re.compile(r"Timeout with MCU '([^']+)' \(eventtime=([\d.]+)\)")
NAMED_MCU = re.compile(r"MCU '([^']+)'")


def number(text):
    try:
        return float(text) if "." in text else int(text)
    except ValueError:
        return None


def parse_stats(text):
    """One Stats line: (globals, boards, heaters). Board and heater figures follow a 'name:' token; the
    toolhead's and the Pi's have no name in front, so they're picked out by key."""
    top, boards, heaters = {}, {}, {}
    name = None
    for token in text.split():
        if token.endswith(":") and "=" not in token:
            name = token[:-1]
            continue
        key, _, value = token.partition("=")
        value = number(value)
        if value is None:
            continue
        if key in GLOBAL_KEYS:
            top[key] = value
        elif key in MCU_KEYS and name:
            boards.setdefault(name, {})[key] = value
        elif name and key in ("target", "temp", "pwm"):
            heaters.setdefault(name, {})[key] = value
    return top, boards, heaters


class Session(object):
    """One Klipper start, from 'Start printer at' to the next one."""

    def __init__(self, started=None, epoch=None, mono=None):
        self.started, self.epoch, self.mono = started, epoch, mono
        self.boards = {}       # name -> {"MCU": chip, "CLOCK_FREQ": .., "SERIAL_BAUD": ..}
        self.config = {}       # section -> {option: value}
        self.stat_count = 0
        self.last_t = None     # the last Stats line's eventtime
        self.events = []       # (kind, text, eventtime of the Stats line before it, Stats entries before it)
        self.reason = None     # how this start came about (FIRMWARE_RESTART, RESTART, service start)
        self.before = []       # the last lines Klipper logged before it

    def wall(self, eventtime):
        """'15:40:07' for a Stats eventtime, from the start line's clock and monotonic time."""
        if self.epoch is None or self.mono is None:
            return "t={:.0f}".format(eventtime)
        return time.strftime("%b %d %H:%M:%S %Z", time.localtime(self.epoch + eventtime - self.mono))

    def motors(self):
        """board -> [(stepper, microsteps)] from the config Klipper logged."""
        found = {}
        for section, options in self.config.items():
            pin = options.get("step_pin")
            if not pin:
                continue
            board = pin.split(":", 1)[0].lstrip("!^~") if ":" in pin else "mcu"
            found.setdefault(board, []).append((section, options.get("microsteps", "?")))
        return found


def read_config(lines):
    """The lines of a '===== Config file =====' block: {section: {option: value}}."""
    sections, section = {}, None
    for line in lines:
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            sections.setdefault(section, {})
        elif section and "=" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition("=")
            sections[section][key.strip()] = value.strip()
    return sections


def stats_time(raw):
    try:
        return float(raw[6:raw.index(b":")])
    except ValueError:
        return None


def parse_entry(raw):
    match = STATS.match(raw.decode("utf-8", "replace").rstrip("\n"))
    if not match:
        return None
    top, boards, heaters = parse_stats(match.group(2))
    return float(match.group(1)), top, boards, heaters


class Scan(object):
    """One cheap pass over the logs, line by line, keeping only what the report needs: the sessions with
    their boards, config, and shutdowns (each with the Stats lines just before it), where the last print
    starts and ends, and the last few minutes of Stats. A day of klippy.log can be 60 MB or more, which
    the Pi can't hold in memory, so Stats lines are only parsed for those stretches."""

    def __init__(self):
        self.sessions = [Session()]
        self.window = collections.deque(maxlen=int(LOOKBACK) + 5)
        self.tail = collections.deque(maxlen=600)
        self.last_print = None
        self.rollover = False
        self.place = (0, 0)
        self.recent = collections.deque(maxlen=200)   # non-Stats lines since the last start

    def _new_session(self, session):
        self._close_print("Klipper restarted before the print finished")
        self.sessions.append(session)
        self.window.clear()
        self.tail.clear()

    def _close_print(self, text, place=None):
        if self.last_print and self.last_print["end"] is None:
            self.last_print["end"], self.last_print["ended"] = place or self.place, text

    def read(self, index, handle):
        offset = 0
        config_lines = None
        for raw in iter(handle.readline, b""):
            offset += len(raw)
            self.place = (index, offset)
            current = self.sessions[-1]
            if config_lines is not None:
                if raw.startswith(b"======================="):
                    self._config(read_config(config_lines))
                    config_lines = None
                else:
                    config_lines.append(raw.decode("utf-8", "replace").rstrip("\n"))
                continue
            if raw.startswith(b"Stats "):
                self.window.append(raw)
                self.tail.append(raw)
                current.stat_count += 1
                current.last_t = stats_time(raw) or current.last_t
                continue
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("Start printer at"):
                match = START.match(line)
                if match:
                    fresh = Session(match.group(1), float(match.group(2)), float(match.group(3)))
                    fresh.reason, fresh.before = start_reason(list(self.recent))
                    self.recent.clear()
                    if not current.stat_count and not current.events:
                        fresh.boards, fresh.config = current.boards, current.config
                        self._close_print("Klipper restarted before the print finished")
                        self.sessions[-1] = fresh
                    else:
                        self._new_session(fresh)
            elif line.strip() and not line.startswith((" ", "\t")):
                self.recent.append(line)
            if line.startswith("=============== Log rollover at"):
                self.rollover = True
            elif line == "===== Config file =====":
                config_lines = []
            elif line.startswith("MCU '"):
                match = MCU_CONFIG.match(line)
                if match:
                    current.boards[match.group(1)] = dict(
                        part.split("=", 1) for part in match.group(2).split() if "=" in part)
            elif line.startswith("Starting SD card print"):
                # virtual_sdcard logs this again on every resume after a pause, with the file position it
                # goes on from. Only a start from position 0, or one in a new session, is a new print.
                match = re.search(r"position (\d+)", line)
                position = int(match.group(1)) if match else 0
                running = (self.last_print and self.last_print["end"] is None
                           and self.last_print["session"] is current)
                if running and position > 0:
                    self.last_print["resumes"] += 1
                else:
                    self._close_print("a new print started before it finished", place=(index, offset - len(raw)))
                    self.last_print = {"session": current, "start": (index, offset), "end": None, "ended": None,
                                       "resumes": 0, "position": position}
            elif line.startswith("Finished SD card print"):
                if self.last_print and self.last_print["session"] is current:
                    self._close_print("finished")
            elif line.startswith("Transition to shutdown state: "):
                text = line[len("Transition to shutdown state: "):].strip()
                entries = [e for e in (parse_entry(r) for r in self.window) if e]
                if entries:
                    entries = [e for e in entries if entries[-1][0] - e[0] <= LOOKBACK]
                current.events.append(("shutdown", text, current.last_t, entries))
                if self.last_print and self.last_print["session"] is current:
                    self._close_print("Klipper shut down: " + text)

    def _config(self, config):
        current = self.sessions[-1]
        if self.rollover and current.config:
            self.rollover = False
            return
        self.rollover = False
        if current.stat_count or current.events:
            self._new_session(Session())
            current = self.sessions[-1]
        current.config = config


def start_reason(lines):
    """How a Klipper start came about, from the lines logged since the start before it, and the last few
    lines logged before the restart itself."""
    marks = [i for i, line in enumerate(lines)
             if line.startswith(("Restarting printer", "Starting Klippy", "Attempting MCU"))]
    if any(line.startswith("Attempting MCU") for line in lines):
        reason = "FIRMWARE_RESTART (Klipper reset its boards and reloaded)"
    elif any(line.startswith("Restarting printer") for line in lines):
        reason = "RESTART (Klipper reloaded its config, asked by a command, Fluidd, or QIDI's software)"
    elif any(line.startswith("Starting Klippy") for line in lines):
        reason = "Klipper's service started (the printer powering on, or the service being restarted)"
    else:
        return None, []
    cut = marks[0] if marks else len(lines)
    skip = ("=====", "Stats ", "Args:", "Git version", "CPU:", "Python:", "Start printer", "Loaded MCU", "MCU '")
    before = [line[:150] for line in lines[:cut] if not line.startswith(skip)][-4:]
    return reason, before


def scan(paths, progress=None):
    """Scan the log files, oldest first. Returns the Scan."""
    result = Scan()
    for index, path in enumerate(paths):
        if progress:
            progress(path)
        with open(path, "rb") as handle:
            result.read(index, handle)
    result.sessions = [s for s in result.sessions if s.stat_count or s.events or s.started]
    return result


def lines_near(paths, last_print, stretches, before=3.0, after=1.0, keep=14):
    """The non-Stats lines Klipper logged during each stretch, by the time of the Stats line before them."""
    found = [[] for _ in stretches]
    (first_file, first_offset), end = last_print["start"], last_print["end"]
    now = None
    for index in range(first_file, len(paths)):
        with open(paths[index], "rb") as handle:
            offset = 0
            if index == first_file:
                handle.seek(first_offset)
                offset = first_offset
            for raw in iter(handle.readline, b""):
                offset += len(raw)
                if end is not None and (index, offset) > end:
                    return found
                if raw.startswith(b"Stats "):
                    now = stats_time(raw) or now
                    continue
                if now is None or not raw.strip():
                    continue
                for n, (start, stop, _, _) in enumerate(stretches):
                    if start - before <= now <= stop + after and len(found[n]) < keep:
                        found[n].append(raw.decode("utf-8", "replace").rstrip()[:160])
    return found


def print_stats(paths, last_print):
    """Second pass: parse the Stats lines of the last print only, from where it started to where it ended."""
    (first_file, first_offset), end = last_print["start"], last_print["end"]
    for index in range(first_file, len(paths)):
        with open(paths[index], "rb") as handle:
            offset = 0
            if index == first_file:
                handle.seek(first_offset)
                offset = first_offset
            for raw in iter(handle.readline, b""):
                offset += len(raw)
                if end is not None and (index, offset) > end:
                    return
                if raw.startswith(b"Stats "):
                    entry = parse_entry(raw)
                    if entry:
                        yield entry


# ------------------------------------------------------------------ figures
def summarize(stats, session):
    """Peak figures over Stats entries, in one pass, so it works on a generator of any length."""
    out = {"seconds": 0.0, "first": None, "cpu_max": None, "cpu_avg": None, "cpu_at": None, "cpu_busy": 0,
           "sysload": None, "memavail": None,
           "stall": 0.0, "stall_at": None, "buffer_min": None, "print_stalls": 0, "boards": {}}
    cpu_max, cpu_time, cpu_span = None, 0.0, 0.0
    out["stretches"] = []   # [start, end, seconds, peak] where Klipper used 80% of a core or more
    stall_first = stall_last = None
    prev = None
    for entry in stats:
        t1, g1, b1, _ = entry
        if out["first"] is None:
            out["first"] = t1
        out["seconds"] = t1 - out["first"]
        if "sysload" in g1:
            out["sysload"] = max(out["sysload"] or 0.0, g1["sysload"])
        if "memavail" in g1:
            mem = g1["memavail"] / 1024.0
            out["memavail"] = mem if out["memavail"] is None else min(out["memavail"], mem)
        if "print_stall" in g1:
            stall_first = g1["print_stall"] if stall_first is None else stall_first
            stall_last = g1["print_stall"]
        for name, figures in b1.items():
            board = out["boards"].setdefault(name, {"awake": 0.0, "task": 0.0, "link": 0.0, "retransmit": 0,
                                                     "invalid": 0, "srtt": 0.0})
            board["awake"] = max(board["awake"], 100.0 * figures.get("mcu_awake", 0) / STATS_INTERVAL)
            task = figures.get("mcu_task_avg", 0) + 3 * figures.get("mcu_task_stddev", 0)
            board["task"] = max(board["task"], 100.0 * task / TASK_MAX)
            board["srtt"] = max(board["srtt"], figures.get("srtt", 0))
        if prev is not None:
            t0, g0, b0, _ = prev
            dt = t1 - t0
            if dt > 0:
                if dt <= 1.5 and "cputime" in g0 and "cputime" in g1:
                    used = g1["cputime"] - g0["cputime"]
                    if cpu_max is None or used / dt > cpu_max:
                        cpu_max, out["cpu_at"] = used / dt, t1
                    if used / dt >= 0.8:
                        out["cpu_busy"] += 1
                        last = out["stretches"][-1] if out["stretches"] else None
                        if last and t1 - last[1] <= 5.0:
                            last[1], last[2], last[3] = t1, last[2] + 1, max(last[3], used / dt)
                        else:
                            out["stretches"].append([t0, t1, 1, used / dt])
                    cpu_time, cpu_span = cpu_time + used, cpu_span + dt
                # Stats come every second while Klipper is busy or hot. A longer gap after a line that still
                # had moves queued means Klipper's main loop didn't get to run.
                if 1.5 < dt < 120 and g0.get("buffer_time", 0) > 0 and dt - 1.0 > out["stall"]:
                    out["stall"], out["stall_at"] = dt - 1.0, t0
                # Homing and probing run one move at a time ("drip" mode), and Klipper reports 0 queued
                # then; print_stall counts the times the queue really ran dry.
                if g1.get("print_time", 0) > g0.get("print_time", 0) and g1.get("buffer_time", 0) > 0:
                    low = g1["buffer_time"]
                    out["buffer_min"] = low if out["buffer_min"] is None else min(out["buffer_min"], low)
                for name, b in b1.items():
                    before = b0.get(name)
                    if not before:
                        continue
                    board = out["boards"][name]
                    resent = max(0, b.get("bytes_retransmit", 0) - before.get("bytes_retransmit", 0))
                    if dt <= 1.5:
                        sent = b.get("bytes_write", 0) - before.get("bytes_write", 0) + resent
                        board["link"] = max(board["link"], sent / dt)
                    board["retransmit"] += resent
                    board["invalid"] += max(0, b.get("bytes_invalid", 0) - before.get("bytes_invalid", 0))
        prev = entry
    out["print_stalls"] = (stall_last - stall_first) if stall_first is not None else 0
    if cpu_max is not None and cpu_span > 0:
        out["cpu_max"], out["cpu_avg"] = 100.0 * cpu_max, 100.0 * cpu_time / cpu_span
    for name, board in out["boards"].items():
        baud = number(session.boards.get(name, {}).get("SERIAL_BAUD", "") or "")
        board["link_pct"] = 100.0 * board["link"] / (baud / 10.0) if baud else None
    return out


def level(value, busy, high):
    if value is None:
        return ""
    return "near its limit" if value >= high else "busy" if value >= busy else "fine"


def describe(summary, session, report, indent="  "):
    if summary["cpu_max"] is not None:
        report("{}Pi: Klipper used up to {:.0f}% of a CPU core at {} ({:.0f}% on average, {} second{} at 80% or "
               "more); system load up to {:.2f} on {} cores; memory free down to {:.0f} MB.".format(
                   indent, summary["cpu_max"], session.wall(summary["cpu_at"]), summary["cpu_avg"],
                   summary["cpu_busy"], "" if summary["cpu_busy"] == 1 else "s", summary["sysload"] or 0, CORES,
                   summary["memavail"] or 0))
    if summary["stall"] >= 0.5:
        report("{}Klipper's main loop stopped for about {:.1f} s at {} with moves queued.".format(
            indent, summary["stall"], session.wall(summary["stall_at"])))
    else:
        report("{}Klipper's main loop never stopped with moves queued.".format(indent))
    if summary["print_stalls"]:
        report("{}The move queue ran dry {} time{} (print_stall): the Pi didn't send moves fast enough.".format(
            indent, summary["print_stalls"], "" if summary["print_stalls"] == 1 else "s"))
    else:
        report("{}The move queue never ran dry (print_stall stayed the same).".format(indent))
    for name in sorted(summary["boards"]):
        b = summary["boards"][name]
        chip = session.boards.get(name, {}).get("MCU", "")
        link = ("{:.0f}% of its serial link".format(b["link_pct"]) if b["link_pct"] is not None
                else "{:.0f} bytes/s".format(b["link"]))
        report("{}Board '{}'{}: busy up to {:.0f}% ({}), task load up to {:.0f}%, {}; {} bytes resent, "
               "{} bad bytes.".format(indent, name, " ({})".format(chip) if chip else "", b["awake"],
                                      level(b["awake"], 50, 80), b["task"], link, b["retransmit"],
                                      b["invalid"]))


# ------------------------------------------------------------------ USB events
UsbEvent = collections.namedtuple("UsbEvent", "epoch stamp action port ids name")


def read_usb_log(path):
    """Plus4 Grease's USB event log: [UsbEvent], oldest first. A disconnect line has no name, so it gets
    the name from the last connect on the same port with the same IDs."""
    events, names = [], {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.rstrip("\n").split(" ", 5)
                if len(parts) < 5:
                    continue
                try:
                    epoch = float(parts[1])
                except ValueError:
                    continue
                name = parts[5] if len(parts) > 5 and parts[5] != "-" else ""
                key = (parts[3], parts[4])
                if parts[2] == "add" and name:
                    names[key] = name
                events.append(UsbEvent(epoch, parts[0], parts[2], parts[3], parts[4], name or names.get(key, "")))
    except OSError:
        return None
    return events


def is_bootloader(event):
    """The Box board shows up as MKS's bootloader (0483:5740, 'MKS COLOR BOOT') for a few seconds every
    time it starts, before Klipper's firmware takes over."""
    return event.ids.startswith("483/5740/") or "BOOT" in event.name.upper()


def outages(events):
    """Each time a device went away and came back on the same port: (gone, back, seconds, rebooted).
    rebooted is True when its bootloader came up on that port before it was back for good."""
    found = []
    for i, gone in enumerate(events):
        if gone.action != "remove" or is_bootloader(gone):
            continue
        rebooted = False
        for later in events[i + 1:]:
            if later.epoch - gone.epoch > 300:
                break
            if later.port != gone.port or later.action != "add":
                continue
            if is_bootloader(later):
                rebooted = True
                continue
            found.append((gone, later, later.epoch - gone.epoch, rebooted))
            break
    return found


def outage_text(gone, back, seconds, rebooted):
    name = back.name or gone.name or "a USB device ({})".format(gone.ids)
    text = "{} was gone for {:.1f} s".format(name, seconds)
    if rebooted:
        text += " and started again from its bootloader, so it lost power or reset"
        if seconds < 5:
            text += "; a gap that short is a power flicker or a reset, not someone switching it off"
    return text


def usb_around(events, session, when):
    """(covered, events near it): covered when the log was already running before this moment."""
    if events is None or when is None or session.epoch is None:
        return False, []
    moment = session.epoch + when - session.mono
    covered = bool(events) and events[0].epoch <= moment
    near = [e for e in events if moment - USB_BEFORE <= e.epoch <= moment + USB_AFTER and e.action != "start"]
    return covered, [(e, e.epoch - moment) for e in near], outages(events)


def usb_text(event, offset=None):
    what = {"add": "connected", "remove": "disconnected"}.get(event.action, event.action)
    timing = ""
    if offset is not None:
        timing = " ({:.1f} s {} the last Stats line)".format(abs(offset), "before" if offset <= 0 else "after")
    return "{} {} on USB port {}{}".format(event.name or "a USB device ({})".format(event.ids), what,
                                           event.port, timing)


# ------------------------------------------------------------------ shutdowns
def explain(message, before, session, usb=(False, [], [])):
    """Plain findings for one shutdown, from the Stats lines just before it and the USB events around it."""
    s = summarize(before, session)
    covered, near = usb[0], usb[1]
    named = NAMED_MCU.search(message)
    board = named.group(1) if named else None
    findings = []
    host_busy = []
    if s["stall"] >= 0.5:
        host_busy.append("Klipper's main loop stopped for about {:.1f} s at {}".format(
            s["stall"], session.wall(s["stall_at"])))
    if s["cpu_max"] is not None and s["cpu_max"] >= 90:
        host_busy.append("Klipper used {:.0f}% of a CPU core".format(s["cpu_max"]))
    if s["sysload"] is not None and s["sysload"] >= CORES:
        host_busy.append("the Pi's load was {:.2f} on {} cores".format(s["sysload"], CORES))
    if s["memavail"] is not None and s["memavail"] < 50:
        host_busy.append("only {:.0f} MB of memory was free".format(s["memavail"]))
    if s["print_stalls"]:
        host_busy.append("the move queue ran dry {} time{}".format(
            s["print_stalls"], "" if s["print_stalls"] == 1 else "s"))
    link_trouble = ["board '{}' resent {} bytes and got {} bad ones".format(n, b["retransmit"], b["invalid"])
                    for n, b in sorted(s["boards"].items()) if b["retransmit"] or b["invalid"]]
    loaded = ["board '{}' was busy {:.0f}% of the time".format(n, b["awake"])
              for n, b in sorted(s["boards"].items()) if b["awake"] >= 60]
    motors = session.motors().get(board, []) if board else []
    motor_text = ", ".join("{} at {} microsteps".format(m, steps) for m, steps in sorted(motors))

    if "ADC out of range" in message:
        findings.append("A temperature reading went past its min_temp or max_temp, or the sensor reading "
                        "broke (unplugged, shorted, or a bad crimp). Last readings: " + ", ".join(
                            "{} {:.1f}°C (target {:.0f})".format(n, h.get("temp", 0), h.get("target", 0))
                            for n, h in sorted(before[-1][3].items())) + "." if before else
                        "A temperature reading went past its min_temp or max_temp, or the sensor broke.")
    elif "Rescheduled timer in the past" in message or "Stepper too far in past" in message:
        findings.append("Board '{}' was asked to step faster than it can.".format(board) + (
            " It drives {}.".format(motor_text) if motor_text else ""))
        findings.extend(loaded)
    elif "Timer too close" in message or "Missed scheduling" in message or "Lost communication" in message \
            or "Timeout with MCU" in message:
        if host_busy:
            findings.append("The Pi fell behind: " + "; ".join(host_busy) + ". Commands then reached the "
                            "board too late.")
        if link_trouble:
            findings.append("The serial link had errors: " + "; ".join(link_trouble) + ". Check that "
                            "board's cable and connectors.")
        if loaded:
            findings.append("A board was heavily loaded: " + "; ".join(loaded) + (
                ". Board '{}' drives {}.".format(board, motor_text) if motor_text else "."))
        usb_board = board and "SERIAL_BAUD" not in session.boards.get(board, {})
        removed = [(e, dt) for e, dt in near if e.action == "remove"]
        if "Lost communication" in message and usb_board and removed:
            back = [o for o in usb[2] if any(o[0] is e for e, _ in removed)] if len(usb) > 2 else []
            findings.insert(0, "Linux saw a USB disconnect just before: " + "; ".join(
                usb_text(e, dt) for e, dt in removed) + ". The board was switched off, unplugged, lost power, "
                "or reset; Klipper then lost it." + "".join(" " + outage_text(*o) + "." for o in back))
        elif "Lost communication" in message and usb_board and covered and not (host_busy or link_trouble):
            findings.append("Board '{}' stopped answering, but Linux saw no USB device disconnect around it, "
                            "so it stayed connected to the Pi: the board itself stopped responding (a firmware "
                            "fault or a hang) rather than being switched off or unplugged.".format(board))
        elif "Lost communication" in message and not (host_busy or link_trouble):
            findings.append("Board '{}' stopped answering without link errors or a stalled Pi before it: most "
                            "likely {}.".format(board, "its USB connection dropped (cable or plug, the board "
                            "losing power or being switched off, or the board resetting)" if usb_board else
                            "its power, its cable coming loose, or the board resetting"))
        if not findings:
            findings.append("Nothing in Klipper's statistics points to the Pi, the link, or the board being "
                            "overloaded. Something sent a command too late without leaving a trace in the "
                            "log, so this needs a Klipper module that names late commands as they're sent.")
    else:
        findings.extend(host_busy + link_trouble + loaded)
    return findings


# ------------------------------------------------------------------ report
def log_files(path, everything):
    path = os.path.expanduser(path)
    if not everything:
        return [path]
    older = sorted(p for p in glob.glob(path + ".*") if re.search(r"\.\d{4}-\d{2}-\d{2}$", p))
    return older + [path]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("log", nargs="?", default=LOG, help="klippy.log to read (default %(default)s)")
    parser.add_argument("--all", action="store_true", help="also read the older days' logs next to it")
    args = parser.parse_args(argv)
    try:
        os.nice(10)  # stay out of Klipper's way on the Pi
    except OSError:
        pass
    paths = [p for p in log_files(args.log, args.all) if os.path.isfile(p)]
    if not paths:
        print("Can't find {}.".format(os.path.expanduser(args.log)))
        return 1

    def progress(path):
        print("Reading {} ({:.0f} MB)...".format(path, os.path.getsize(path) / 1e6))
        sys.stdout.flush()

    result = scan(paths, progress)
    sessions = result.sessions
    report = print
    report("")
    if not sessions:
        report("No Klipper starts found in the log.")
        return 0
    latest = sessions[-1]
    starts = sum(1 for s in sessions if s.started)
    report("Klipper started {} time{} in {}; the last start was {}.".format(
        starts, "" if starts == 1 else "s", "these logs" if len(paths) > 1 else "this log",
        latest.started or "before the log begins"))
    report("")
    report("Boards and motors:")
    configured = next((s for s in reversed(sessions) if s.boards or s.config), latest)
    motors = configured.motors()
    for name in sorted(set(configured.boards) | set(motors)):
        constants = configured.boards.get(name, {})
        mhz = number(constants.get("CLOCK_FREQ", "") or "")
        report("  '{}': {}{}{}".format(
            name, constants.get("MCU", "chip unknown"), " at {:.0f} MHz".format(mhz / 1e6) if mhz else "",
            ", serial {} baud".format(constants["SERIAL_BAUD"]) if "SERIAL_BAUD" in constants else ""))
        for motor, steps in sorted(motors.get(name, [])):
            report("      {} at {} microsteps".format(motor, steps))

    report("")
    found = result.last_print
    if found:
        session = found["session"]
        summary = summarize(print_stats(paths, found), session)
        ended = found["ended"] or "no finish line yet (still running, or cancelled)"
        length = summary["seconds"]
        resumes = found.get("resumes", 0)
        report("Last print: started {}{}, {} of Stats{}, {}.".format(
            session.wall(summary["first"]) if summary["first"] is not None else "?",
            " at file position {}".format(found["position"]) if found.get("position") else "",
            "{:.0f} min".format(length / 60.0) if length >= 120 else "{:.0f} s".format(length),
            ", resumed {} time{} after a pause".format(resumes, "" if resumes == 1 else "s") if resumes else "",
            ended))
        describe(summary, session, report)
        stretches = sorted(summary["stretches"], key=lambda s: -s[2])[:3]
        if stretches:
            report("")
            report("  When Klipper used 80% of a core or more (longest first), and what it logged then:")
            for (start, stop, seconds, peak), lines in zip(stretches, lines_near(paths, found, stretches)):
                report("    {} to {}: {} s, peak {:.0f}%".format(
                    session.wall(start), session.wall(stop)[-12:], seconds, 100.0 * peak))
                for line in lines or ["(nothing logged)"]:
                    report("        " + line)
    else:
        report("No print in {}. The last {} s of Stats instead:".format(
            "these logs" if len(paths) > 1 else "this log", len(result.tail)))
        describe(summarize((e for e in (parse_entry(r) for r in result.tail) if e), latest), latest, report)

    usb_events = read_usb_log(os.path.join(os.path.dirname(paths[-1]), USB_LOG))
    started = [s for s in sessions if s.started][-10:]
    if started:
        report("")
        report("Klipper starts (the last {}):".format(len(started)))
    for session in started:
        report("  {}: {}".format(time.strftime("%b %d %H:%M:%S %Z", time.localtime(session.epoch)),
                                 session.reason or "how it started isn't in the log"))
        for line in session.before:
            report("      logged before it: " + line)
        if usb_events:
            for event in [e for e in usb_events if session.epoch - 30 <= e.epoch <= session.epoch and
                          e.action != "start"]:
                report("      USB {:.1f} s before: {}".format(session.epoch - event.epoch, usb_text(event)))
    report("")
    if usb_events is None:
        report("No USB event log yet (Plus4 Grease's install adds it), so USB disconnects can't be matched.")
    else:
        shown = [e for e in usb_events if e.action != "start"][-5:]
        report("USB events: {} in {}{}".format(
            len([e for e in usb_events if e.action != "start"]), USB_LOG, ", the last 5:" if shown else "."))
        for event in shown:
            report("  {} UTC: {}".format(event.stamp.replace("T", " ").rstrip("Z")[:19], usb_text(event)))
        gaps = [o for o in outages(usb_events) if not o[0].ids.startswith("1a40/")][-5:]
        if gaps:
            report("  Devices that went away and came back (the last {}):".format(len(gaps)))
            for gone, back, seconds, rebooted in gaps:
                report("    {} UTC: {}.".format(gone.stamp.replace("T", " ").rstrip("Z")[:19],
                                               outage_text(gone, back, seconds, rebooted)))

    shutdowns = [(session, event) for session in sessions for event in session.events if event[0] == "shutdown"]
    report("")
    if not shutdowns:
        report("No shutdowns in {}.".format("these logs" if len(paths) > 1 else "this log")
               + ("" if args.all else " (--all reads the older days too.)"))
        return 0
    report("Shutdowns ({}, the last 5 shown):".format(len(shutdowns)))
    for session, (_, text, when, before) in shutdowns[-5:]:
        report("")
        report("  {}: {}".format(session.wall(when) if when is not None else "at startup", text.splitlines()[0]))
        usb = usb_around(usb_events, session, when)
        for finding in explain(text, before, session, usb):
            report("    - " + finding)
        others = [(e, dt) for e, dt in usb[1] if not (e.action == "remove" and "Lost communication" in text)]
        for event, offset in others:
            report("    - USB: " + usb_text(event, offset))
    return 0


if __name__ == "__main__":
    sys.exit(main())
