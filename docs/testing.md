# Test log

Each release is tried on real printers before it's called tested. Add a line for every printer it's run on.

| Version | Date | Printer | Firmware | What was run | Result |
|---|---|---|---|---|---|
| 0.1.0 | 2026-11-21 | Plus 4, Beacon probe conversion, QIDI Box | V2.1.1 | `install --dry-run`, `install`, a Box print | Dry run read the firmware with `sudo` and listed print start `available`, bed mesh `skipped` (the Beacon conversion's `G29` isn't QIDI's). Install backed up `gcode_macro.cfg`, applied print start, and Klipper restarted ready. The print with the Box started normally and finished without problems. |
| 0.1.0 | 2026-11-21 | Plus 4, Beacon probe conversion, QIDI Box | V2.1.1 | `uninstall`, `status`, `install` | Uninstall put QIDI's print start lines back and Klipper restarted ready; `status` showed print start `available` again. A second install backed up the file, applied print start again, and Klipper restarted ready. |
| 0.2.0 | 2026-11-21 | Plus 4, Beacon probe conversion, QIDI Box | V2.1.1 | `install --dry-run --replace-own-speeds`, `install --replace-own-speeds` (upgrade from 0.1.0) | Print start stayed `applied`, bed mesh save `skipped`. Both speed changes were skipped without the switch: the conversion had `speed: 200` under `[z_tilt]` and its own `[bed_mesh]` with speed 150. With the switch, install replaced both, backed up `printer.cfg`, Klipper restarted ready, and Klipper's loaded settings showed speed 300 under `[z_tilt]` and `[bed_mesh]`. |
| 0.2.0 | 2026-11-21 | Plus 4, Beacon probe conversion, QIDI Box | V2.1.1 | A print (about 45 min) after installing | Z tilt and the Beacon mesh ran at 300 mm/s between points, the print started and finished normally. |
| 0.3.0 | 2026-11-21 | Plus 4, Beacon probe conversion, QIDI Box | V2.1.1 | `install --dry-run`, `install`, Box switched off and on, `FIRMWARE_RESTART` | Dry run listed only the USB event log as `available`. After install, udev logged every event with names: Box off removed the Box board (`1d50:614e`) and then the Box's own USB hub (`1a40:0801`); Box on brought the hub back, the Box board as its bootloader ("MKS COLOR BOOT", `0483:5740`) for 2.5 s, then as "Klipper QIDI_BOX_V1_1.1.1"; `FIRMWARE_RESTART` reset the Beacon (`04d8:e72b`), which reconnected 6 s later. No serial numbers in the log. Klipper logged no shutdown for the Box going away. |

Still untested: the bed mesh save change (needs a printer with QIDI's stock `G29`), the probe speeds with QIDI's stock probe, and any stock Plus 4.

## Speed test (`tools/speed_test.py`), for faster probe moves

Bill's Plus 4 (Beacon conversion, V2.1.1, 32 microsteps, 20000 mm/s² max accel). A drift is how far a motor's step count moved between two homes; 32 microsteps is one full step.

| Date | Run | Result |
|---|---|---|
| 2026-11-21 | Homing alone, 5 times | Repeats within 1 (A) and 14 (B) microsteps. |
| 2026-11-21 | `--locate` over the old travel area (X 18-287, Y 18-305) at 100 mm/s, 5000 mm/s² | Only the back edge at Y 305 lost steps: B -911, about 7 slips of 4 full steps. That edge runs through QIDI's back-left no-print zone (Y 302-305), where the toolhead meets something; the other edges and both diagonals stayed within about 20 microsteps. The test now never goes past Y 301 or X 292. |
| 2026-11-21 | `--locate` over the probe area (X 22-283, Y 41-301, the bed mesh area shifted by the Beacon's -18.8 mm Y offset) at 100 mm/s, 5000 mm/s² | No lost steps. B stayed within 22 microsteps on every segment, Y 301 included. A came back one full step off (±32-33) after every segment, alternating sign: sensorless homing only checks for a stall once per full step, so a home can land a step either way. The test had counted anything past 32 as lost steps and wrongly flagged five segments; it now counts 64 or more (half of a 4-full-step slip) as lost. |
| 2026-11-21 | Speed test over the probe area (X 22-283, Y 41-301), 150 to 500 mm/s at 20000 mm/s², 5 passes of both diagonals and the edges each | No lost steps at any speed. Every drift was within 6 microsteps except at 200 mm/s (A -32, B +30), one full step on each, which is homing. Highest speed tested: 500 mm/s; no limit was reached. Plus4 Grease 0.2.0 sets the Z tilt and bed mesh travel to 300 mm/s from this. |

## Klipper report (`tools/klipper_report.py`), Bill's Plus 4, 2026-11-21

- Last print (30 min, Beacon conversion, one Box): every board under 2% busy, the mainboard's serial link at 20% at most, no resent or bad bytes. On the mainboard's Linux processor (RK3328), Klipper averaged 24% of a core and peaked at 97% for short stretches during print start: Z tilt probing (9 s), the Beacon model save with SAVE_CONFIG_QD (7 s), and 3 s with nothing logged. Klipper's main loop never paused: a Stats line came every second throughout, including the config save. The move queue never ran dry.
- Shutdowns over six days: one, "Lost communication with MCU 'mcu_box1'" on Nov 18 at 13:51 UTC, very likely a household power flicker rebooting the Box; Klipper stayed shut down 9.1 h. A flicker on Nov 21 at 13:06 UTC rebooted the Box too; QIDI's software restarted Klipper's service 17 s later and a print in its start sequence was cancelled. Switching the Box off by hand gave the same service restart 16 s later.
