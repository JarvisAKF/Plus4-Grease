#!/usr/bin/env python3
"""X/Y speed test for the QIDI Plus 4: how fast can the toolhead travel without losing steps?

Run on the printer as mks, with the bed clear:

    python3 ~/plus4-grease/tools/speed_test.py

It homes, raises the bed clear of the nozzle, records where the X/Y motors think they are, then runs a
pattern of moves across the bed at each speed in turn. After each speed it re-homes X and Y and compares:
a motor that lost steps reports a different position at the same endstop. It stops at the first speed
that loses steps.

It changes no files. It uses Klipper's own commands through Moonraker, puts the speed and acceleration
limits back afterwards, and writes its results to ~/plus4-grease-speed-test-<date>.txt.

The method (home, move, re-home, compare the motors' step counts) is the one from Ellis' print tuning guide.
This file runs on the printer's Python 3.7, so it uses 3.7 syntax and library features only.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MOONRAKER = "http://127.0.0.1:7125"
MARGIN = 20.0  # mm kept clear of each end of travel
STEPPERS = ("stepper_x", "stepper_y")  # on CoreXY, the A and B motors


def get(path):
    with urllib.request.urlopen(MOONRAKER + path, timeout=15) as reply:
        return json.load(reply)["result"]


def gcode(script, timeout=900):
    """Runs G-code and returns when Klipper has finished it (scripts end with M400 where moves matter)."""
    query = urllib.parse.urlencode({"script": script})
    request = urllib.request.Request(MOONRAKER + "/printer/gcode/script?" + query, data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            reply.read()
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", "replace")
        raise SystemExit("Klipper refused {!r}: {}".format(script.splitlines()[0], message))


def mcu_positions():
    """GET_POSITION's 'mcu:' line holds each motor's step count. Klipper sends all its lines as one
    message, each starting with '// '."""
    since = time.time() - 1
    gcode("GET_POSITION")
    for _ in range(20):
        for entry in reversed(get("/server/gcode_store?count=40")["gcode_store"]):
            found = re.search(r"mcu: ([^\n]*)", entry.get("message", ""))
            if found and entry.get("time", 0) >= since:
                counts = dict(re.findall(r"(\w+):(-?\d+)", found.group(1)))
                return {name: int(counts[name]) for name in STEPPERS}
        time.sleep(0.25)
    recent = [entry.get("message", "")[:120] for entry in get("/server/gcode_store?count=5")["gcode_store"]]
    raise SystemExit("Couldn't read GET_POSITION's output from Moonraker. Its last messages were:\n  "
                     + "\n  ".join(recent))


def rehome(park):
    gcode("G90\nG1 X{:.1f} Y{:.1f} F6000\nM400\nG28 X Y\nM400".format(park[0], park[1]))
    return mcu_positions()


def pattern(xmin, xmax, ymin, ymax):
    xmid, ymid = (xmin + xmax) / 2, (ymin + ymax) / 2
    return [(xmin, ymin), (xmax, ymax), (xmin, ymax), (xmax, ymin),   # both diagonals
            (xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax),   # the edges
            (xmin, ymin), (xmid, ymax), (xmid, ymin), (xmax, ymid),   # crosses through the middle
            (xmin, ymid), (xmin, ymin)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--speeds", default="150,200,250,300,350,400,450,500",
                        help="mm/s, comma separated, slowest first (default %(default)s)")
    parser.add_argument("--accel", type=float, default=None,
                        help="mm/s^2 for the test moves (default: the printer's max_accel)")
    parser.add_argument("--repeats", type=int, default=5, help="times through the pattern at each speed")
    parser.add_argument("--yes", action="store_true", help="don't ask before moving")
    args = parser.parse_args(argv)
    speeds = [float(s) for s in args.speeds.split(",") if s.strip()]

    if get("/printer/info").get("state") != "ready":
        raise SystemExit("Klipper isn't ready.")
    status = get("/printer/objects/query?print_stats=state&toolhead=max_velocity,max_accel,"
                 "square_corner_velocity&configfile=settings")["status"]
    if status["print_stats"]["state"] in ("printing", "paused"):
        raise SystemExit("The printer is {}; run this when it's idle.".format(status["print_stats"]["state"]))
    settings = status["configfile"]["settings"]
    toolhead = status["toolhead"]
    limits = {name: (float(settings[name]["position_min"]), float(settings[name]["position_max"]))
              for name in STEPPERS}
    xmin, xmax = limits["stepper_x"][0] + MARGIN, limits["stepper_x"][1] - MARGIN
    ymin, ymax = limits["stepper_y"][0] + MARGIN, limits["stepper_y"][1] - MARGIN
    max_velocity = float(settings["printer"]["max_velocity"])
    accel = args.accel or float(settings["printer"]["max_accel"])
    microsteps = int(settings["stepper_x"]["microsteps"])
    full_steps = int(settings["stepper_x"].get("full_steps_per_rotation", 200))
    mm_per_microstep = float(settings["stepper_x"]["rotation_distance"]) / (full_steps * microsteps)
    speeds = [s for s in speeds if s <= max_velocity]
    park = (xmin, ymin)

    print("Speeds {} mm/s at {:.0f} mm/s^2, {} times through the pattern each, inside X {:.0f}-{:.0f} and "
          "Y {:.0f}-{:.0f}.".format(", ".join("{:.0f}".format(s) for s in speeds), accel, args.repeats,
                                    xmin, xmax, ymin, ymax))
    print("The toolhead will move fast across the whole bed. Clear the bed and keep hands out.")
    if not args.yes and input("Type yes to start: ").strip().lower() != "yes":
        print("Not started.")
        return 1

    lines = []

    def log(line):
        print(line)
        sys.stdout.flush()
        lines.append(line)

    original = "SET_VELOCITY_LIMIT VELOCITY={} ACCEL={} SQUARE_CORNER_VELOCITY={}".format(
        toolhead["max_velocity"], toolhead["max_accel"], toolhead["square_corner_velocity"])
    try:
        log("Homing...")
        gcode("G28\nG90\nG1 Z10 F600\nM400")
        gcode("SET_VELOCITY_LIMIT VELOCITY=100 ACCEL=5000")
        # Homing alone first: re-home with no moves in between. If that doesn't land within a full step,
        # nothing after it can tell lost steps from homing, so stop and say so.
        first = rehome(park)
        homes = [first]
        for _ in range(4):
            homes.append(rehome(park))
        log("Homing X and Y 5 times with no moves in between (motor step counts relative to the first):")
        for name, label in zip(STEPPERS, ("A (stepper_x)", "B (stepper_y)")):
            offsets = [h[name] - first[name] for h in homes]
            log("  {}: {}".format(label, ", ".join("{:+d}".format(o) for o in offsets)))
        spread = {name: max(h[name] for h in homes) - min(h[name] for h in homes) for name in STEPPERS}
        bad = [name for name in STEPPERS if spread[name] > microsteps]
        if bad:
            for name in bad:
                slip = 4 * microsteps
                offsets = [h[name] - first[name] for h in homes]
                whole = all(abs(o - slip * round(o / slip)) <= microsteps / 4 for o in offsets)
                log("Homing isn't repeatable on {}: it varied by {} microsteps ({:.1f} full steps, {:.2f} mm) with "
                    "no moves at all.{}".format(
                        "motor A" if name == "stepper_x" else "motor B", spread[name], spread[name] / microsteps,
                        spread[name] * mm_per_microstep,
                        " The differences are whole multiples of 4 full steps, the jump a stepper makes when it "
                        "slips, so the motor is most likely slipping while homing that axis." if whole else ""))
            log("A speed test can't separate lost steps from homing on this printer, so it stops here. Homing "
                "needs looking at first.")
            return 1
        threshold = {name: microsteps for name in STEPPERS}
        log("Homing repeats within {} / {} microsteps (A / B); a drift beyond one full step ({} microsteps) "
            "counts as lost steps.".format(spread["stepper_x"], spread["stepper_y"], microsteps))
        first = homes[-1]
        log("{:>7}  {:>14}  {:>14}  result".format("mm/s", "A drift", "B drift"))
        safe = None
        for speed in speeds:
            gcode("SET_VELOCITY_LIMIT VELOCITY={:.0f} ACCEL={:.0f}".format(speed, accel))
            moves = "\n".join("G1 X{:.1f} Y{:.1f} F{:.0f}".format(x, y, speed * 60)
                              for x, y in pattern(xmin, xmax, ymin, ymax) * args.repeats)
            gcode("G90\n" + moves + "\nM400")
            gcode("SET_VELOCITY_LIMIT VELOCITY=100 ACCEL=5000")
            after = rehome(park)
            drift = {name: after[name] - first[name] for name in STEPPERS}
            lost = any(abs(drift[name]) > threshold[name] for name in STEPPERS)
            log("{:7.0f}  {:>6} ({:+.2f}mm)  {:>6} ({:+.2f}mm)  {}".format(
                speed, drift["stepper_x"], drift["stepper_x"] * mm_per_microstep,
                drift["stepper_y"], drift["stepper_y"] * mm_per_microstep,
                "LOST STEPS" if lost else "ok"))
            if lost:
                break
            safe = speed
            first = after
        if safe is None:
            log("Lost steps at the first speed; nothing faster than QIDI's settings is safe.")
        else:
            log("Highest speed without lost steps: {:.0f} mm/s at {:.0f} mm/s^2.".format(safe, accel))
    finally:
        gcode(original + "\nM400")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = os.path.expanduser("~/plus4-grease-speed-test-{}.txt".format(stamp))
        with open(path, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        print("Speed and acceleration limits put back. Results saved to {}".format(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
