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
import glob
import os
import re
import sys
import time

LOG = "~/printer_data/logs/klippy.log"
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
        self.stats = []        # (eventtime, globals, boards, heaters)
        self.events = []       # (index into stats, kind, text)

    def wall(self, eventtime):
        """'15:40:07' for a Stats eventtime, from the start line's clock and monotonic time."""
        if self.epoch is None or self.mono is None:
            return "t={:.0f}".format(eventtime)
        return time.strftime("%H:%M:%S", time.localtime(self.epoch + eventtime - self.mono))

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


def read_config(lines, start):
    """The '===== Config file =====' block from start: (sections, index after it)."""
    sections, section = {}, None
    i = start + 1
    while i < len(lines) and not lines[i].startswith("======================="):
        line = lines[i].rstrip("\n")
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            sections.setdefault(section, {})
        elif section and "=" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition("=")
            sections[section][key.strip()] = value.strip()
        i += 1
    return sections, i


def parse(lines):
    sessions = [Session()]
    rollover = False
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        current = sessions[-1]
        if line.startswith("=============== Log rollover at"):
            # A new day's file repeats the config and board lines at its top; the session goes on.
            rollover = True
            i += 1
            continue
        match = START.match(line)
        if match:
            fresh = Session(match.group(1), float(match.group(2)), float(match.group(3)))
            # The config and board lines come before the start line; keep them with the new session.
            if not current.stats and not current.events:
                fresh.boards, fresh.config = current.boards, current.config
                sessions[-1] = fresh
            else:
                sessions.append(fresh)
            i += 1
            continue
        if line == "===== Config file =====":
            config, i = read_config(lines, i)
            if rollover and current.config:
                rollover = False
                i += 1
                continue
            rollover = False
            if current.stats or current.events:
                current = Session()
                sessions.append(current)
            current.config = config
            i += 1
            continue
        match = MCU_CONFIG.match(line)
        if match:
            constants = dict(part.split("=", 1) for part in match.group(2).split() if "=" in part)
            current.boards[match.group(1)] = constants
        match = STATS.match(line)
        if match:
            top, boards, heaters = parse_stats(match.group(2))
            current.stats.append((float(match.group(1)), top, boards, heaters))
        elif line.startswith("Starting SD card print"):
            current.events.append((len(current.stats), "print_start", line))
        elif line.startswith("Finished SD card print"):
            current.events.append((len(current.stats), "print_end", line))
        else:
            match = SHUTDOWN.match(line)
            if match:
                current.events.append((len(current.stats), "shutdown", match.group(1).strip()))
            match = TIMEOUT.match(line)
            if match:
                current.events.append((len(current.stats), "timeout", match.group(1)))
        i += 1
    return [s for s in sessions if s.stats or s.events or s.started]


# ------------------------------------------------------------------ figures
def summarize(stats, session):
    """Peak figures over a run of Stats lines."""
    out = {"seconds": 0.0, "cpu_max": None, "cpu_avg": None, "sysload": None, "memavail": None,
           "stall": 0.0, "stall_at": None, "buffer_min": None, "print_stalls": 0, "boards": {}}
    if not stats:
        return out
    out["seconds"] = stats[-1][0] - stats[0][0]
    cpu, cpu_time, cpu_span = [], 0.0, 0.0
    for (t0, g0, b0, h0), (t1, g1, b1, h1) in zip(stats, stats[1:]):
        dt = t1 - t0
        if dt <= 0:
            continue
        if dt <= 1.5 and "cputime" in g0 and "cputime" in g1:
            used = g1["cputime"] - g0["cputime"]
            cpu.append(used / dt)
            cpu_time, cpu_span = cpu_time + used, cpu_span + dt
        # Stats come every second while Klipper is busy or hot. A longer gap after a line that still had
        # moves queued means Klipper's main loop didn't get to run.
        if 1.5 < dt < 120 and g0.get("buffer_time", 0) > 0:
            if dt - 1.0 > out["stall"]:
                out["stall"], out["stall_at"] = dt - 1.0, t0
        if g1.get("print_time", 0) > g0.get("print_time", 0) and "buffer_time" in g1:
            low = g1["buffer_time"]
            out["buffer_min"] = low if out["buffer_min"] is None else min(out["buffer_min"], low)
        for name, b in b1.items():
            prev = b0.get(name)
            board = out["boards"].setdefault(name, {"awake": 0.0, "task": 0.0, "link": 0.0, "retransmit": 0,
                                                     "invalid": 0, "srtt": 0.0})
            if prev and dt <= 1.5:
                sent = (b.get("bytes_write", 0) - prev.get("bytes_write", 0)
                        + b.get("bytes_retransmit", 0) - prev.get("bytes_retransmit", 0))
                board["link"] = max(board["link"], sent / dt)
            if prev:
                board["retransmit"] += max(0, b.get("bytes_retransmit", 0) - prev.get("bytes_retransmit", 0))
                board["invalid"] += max(0, b.get("bytes_invalid", 0) - prev.get("bytes_invalid", 0))
    for _, g, b, _ in stats:
        if "sysload" in g:
            out["sysload"] = max(out["sysload"] or 0.0, g["sysload"])
        if "memavail" in g:
            mem = g["memavail"] / 1024.0
            out["memavail"] = mem if out["memavail"] is None else min(out["memavail"], mem)
        for name, figures in b.items():
            board = out["boards"].setdefault(name, {"awake": 0.0, "task": 0.0, "link": 0.0, "retransmit": 0,
                                                     "invalid": 0, "srtt": 0.0})
            board["awake"] = max(board["awake"], 100.0 * figures.get("mcu_awake", 0) / STATS_INTERVAL)
            task = figures.get("mcu_task_avg", 0) + 3 * figures.get("mcu_task_stddev", 0)
            board["task"] = max(board["task"], 100.0 * task / TASK_MAX)
            board["srtt"] = max(board["srtt"], figures.get("srtt", 0))
    stalls = [g["print_stall"] for _, g, _, _ in stats if "print_stall" in g]
    out["print_stalls"] = (stalls[-1] - stalls[0]) if stalls else 0
    if cpu:
        out["cpu_max"], out["cpu_avg"] = 100.0 * max(cpu), 100.0 * cpu_time / cpu_span
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
        report("{}Pi: Klipper used up to {:.0f}% of a CPU core ({:.0f}% on average); system load up to {:.2f} "
               "on {} cores; memory free down to {:.0f} MB.".format(
                   indent, summary["cpu_max"], summary["cpu_avg"], summary["sysload"] or 0, CORES,
                   summary["memavail"] or 0))
    if summary["stall"] >= 0.5:
        report("{}Klipper's main loop stopped for about {:.1f} s at {} with moves queued.".format(
            indent, summary["stall"], session.wall(summary["stall_at"])))
    else:
        report("{}Klipper's main loop never stopped with moves queued.".format(indent))
    if summary["buffer_min"] is not None:
        report("{}Moves queued ahead of the motors: never under {:.2f} s{}.".format(
            indent, summary["buffer_min"],
            " (it ran nearly dry)" if summary["buffer_min"] < 0.1 else ""))
    if summary["print_stalls"]:
        report("{}The move queue ran dry {} times (print_stall): the Pi didn't send moves fast enough.".format(
            indent, summary["print_stalls"]))
    for name in sorted(summary["boards"]):
        b = summary["boards"][name]
        chip = session.boards.get(name, {}).get("MCU", "")
        link = ("{:.0f}% of its serial link".format(b["link_pct"]) if b["link_pct"] is not None
                else "{:.0f} bytes/s".format(b["link"]))
        report("{}Board '{}'{}: busy up to {:.0f}% ({}), task load up to {:.0f}%, {}; {} bytes resent, "
               "{} bad bytes.".format(indent, name, " ({})".format(chip) if chip else "", b["awake"],
                                      level(b["awake"], 50, 80), b["task"], link, b["retransmit"],
                                      b["invalid"]))


# ------------------------------------------------------------------ shutdowns
def explain(message, before, session):
    """Plain findings for one shutdown, from the Stats lines just before it."""
    s = summarize(before, session)
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
    if s["buffer_min"] is not None and s["buffer_min"] < 0.1:
        host_busy.append("the moves queued ahead of the motors fell to {:.2f} s".format(s["buffer_min"]))
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
        if "Lost communication" in message and not (host_busy or link_trouble):
            findings.append("Board '{}' stopped answering without link errors or a stalled Pi before it: "
                            "most likely its power, its cable coming loose, or the board resetting."
                            .format(board))
        if not findings:
            findings.append("Nothing in Klipper's statistics points to the Pi, the link, or the board being "
                            "overloaded. Something sent a command too late without leaving a trace in the "
                            "log, so this needs a Klipper module that names late commands as they're sent.")
    else:
        findings.extend(host_busy + link_trouble + loaded)
    return findings


# ------------------------------------------------------------------ report
def last_print(session):
    starts = [i for i, kind, _ in session.events if kind == "print_start"]
    if not starts:
        return None
    start = starts[-1]
    end = next((i for i, kind, _ in session.events if i >= start and kind in ("print_end", "shutdown")
                and (i, kind) != (start, "print_start")), len(session.stats))
    return start, end


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
    lines = []
    for path in log_files(args.log, args.all):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                lines.extend(handle.readlines())
        except OSError as error:
            print("Can't read {}: {}".format(path, error.strerror))
            return 1
    sessions = parse(lines)
    report = print
    if not sessions:
        print("No Klipper starts found in the log.")
        return 0

    latest = sessions[-1]
    starts = sum(1 for s in sessions if s.started)
    report("Klipper started {} time{} in this log; the last start was {}.".format(
        starts, "" if starts == 1 else "s", latest.started or "before the log begins"))
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
    found = None
    for session in reversed(sessions):
        span = last_print(session)
        if span:
            found = session, span
            break
    if found:
        session, (start, end) = found
        stats = session.stats[start:end]
        ended = next((text for i, kind, text in session.events if i == end and kind in ("print_end", "shutdown")),
                     "still running when the log ends")
        if ended.startswith("Finished"):
            ended = "finished"
        elif not ended.startswith("still"):
            ended = "Klipper shut down: " + ended.splitlines()[0]
        report("Last print: started {}, {:.0f} min of Stats, {}.".format(
            session.wall(stats[0][0]) if stats else "?", (stats[-1][0] - stats[0][0]) / 60.0 if stats else 0,
            ended))
        describe(summarize(stats, session), session, report)
    else:
        report("No print in this log. Busiest stretch of Stats instead:")
        describe(summarize(latest.stats, latest), latest, report)

    shutdowns = [(session, i, text) for session in sessions for i, kind, text in session.events
                 if kind == "shutdown"]
    report("")
    if not shutdowns:
        report("No shutdowns in this log." + ("" if args.all else " (--all reads the older days too.)"))
        return 0
    report("Shutdowns ({}, the last 5 shown):".format(len(shutdowns)))
    for session, index, text in shutdowns[-5:]:
        before = [entry for entry in session.stats[:index]
                  if session.stats[index - 1][0] - entry[0] <= LOOKBACK] if index else []
        when = session.wall(session.stats[index - 1][0]) if index else "at startup"
        report("")
        report("  {}: {}".format(when, text.splitlines()[0]))
        for finding in explain(text, before, session):
            report("    - " + finding)
    return 0


if __name__ == "__main__":
    sys.exit(main())
