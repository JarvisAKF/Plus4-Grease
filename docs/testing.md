# Test log

Each release is tried on real printers before it's called tested. Add a line for every printer it's run on.

| Version | Date | Printer | Firmware | What was run | Result |
|---|---|---|---|---|---|
| 0.1.0 | 2026-11-21 | Plus 4, Beacon probe conversion, QIDI Box | V2.1.1 | `install --dry-run`, `install`, a Box print | Dry run read the firmware with `sudo` and listed print start `available`, bed mesh `skipped` (the Beacon conversion's `G29` isn't QIDI's). Install backed up `gcode_macro.cfg`, applied print start, and Klipper restarted ready. The print with the Box started normally. |

Still untested: the bed mesh change (needs a printer with QIDI's stock `G29`), `uninstall` on a printer, and any stock Plus 4.
