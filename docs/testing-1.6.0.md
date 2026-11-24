# Testing on firmware 1.6.0

QIDI's 1.6.0 (November 2024) is the Plus 4 from before the QIDI Box, so Plus4 Grease keeps a separate change list for it: [`grease/edits_v160.py`](../grease/edits_v160.py). It's written and tested against QIDI's published 1.6.0 files (`stock/plus4-1.6.0/`) alone, and nothing made for 1.8.1 and later reaches it. What's different about 1.6.0 is in [plus4-notes.md](plus4-notes.md#firmware-160).

## What the 1.6.0 list does

| Change | On 1.6.0 |
|---|---|
| Bed mesh: 0.5 s instead of 5 s before saving a new mesh | standard |
| Z tilt: 300 mm/s between probe points | standard. 1.6.0's print start doesn't run Z tilt, so it only counts when Z tilt is run some other way |
| Bed mesh: 300 mm/s between probe points | standard. 1.6.0's print start measures a mesh every print |
| USB event log | standard |
| `--board-fan` | opt-in |
| `--balanced-chamber` | opt-in |
| Print start: no 1.6 s wait clearing the Box runout flags | not offered: that loop isn't in 1.6.0 |
| Print start: 2 Box purges instead of 5 | not offered: 1.6.0 has no `EXTRUSION_AND_FLUSH` |
| `--box-dry` (drying, print-start check, cool-down lock) | not offered: 1.6.0 has no Box support |
| New Fluidd on port 81 | the same as on other firmware; the Box card stays hidden with no Box |

## Done on a computer (0.13.1)

All against QIDI's 1.6.0 `printer.cfg` and `gcode_macro.cfg` (`tests/test_v160.py`):

- Every change finds its stock block exactly once, applies once, and undoes to QIDI's exact text, alone and all together.
- The standard changes alter only `G4 P5000` to `G4 P500` in `G29` and the two `speed` lines.
- Install on a pretend 1.6.0 printer applies the three standard changes and the USB log, records `V1.6.0`, and shows no Box lines; `status` uses the recorded list; `uninstall` gives back QIDI's files byte for byte. `--board-fan` and `--balanced-chamber` install and come out again. `--box-dry` does nothing.
- The main list run on 1.6.0 (which happens with `--any-firmware` if the version can't be read) applies the same changes the same way and leaves the Box ones alone.
- `tools/config_diff.py --firmware 1.6.0` finds no differences on QIDI's files.
- 1.6.0's Klipper (`QIDITECH/klipper` `a363ac0`) has what the board fan and balanced chamber use: `temperature_combined`, `temperature_mcu`, `fan_generic`, the TMC2240 driver temperature and per-stepper enable status.

## Still to do on a 1.6.0 printer

Run as `mks`. Each step changes nothing unless it says so. Paste the output; the tools hide serial numbers, but read it before posting.

1. **The firmware version.** `sudo cat /root/xindi/version`. Plus4 Grease reads the `soc = ...` line. Expected `soc = V1.6.0`; if the file is missing or says something else, stop and send what it says. Only V2.1.1's file has been seen.
2. **Get Plus4 Grease.** `git clone https://github.com/JarvisAKF/Plus4-Grease ~/plus4-grease`, or `cd ~/plus4-grease && git pull` if it's there.
3. **Config comparison.** `python3 ~/plus4-grease/tools/config_diff.py --firmware 1.6.0`. On a stock 1.6.0 printer, expect only your own changes (bed meshes, input shaper and PID results in the SAVE_CONFIG block, anything you added).
4. **Dry run.** `bash ~/plus4-grease/install.sh install --dry-run`. Expect the 1.6.0 line ("from before the QIDI Box ... its own 1.6.0 change list"), then `available` for the bed mesh save wait, Z tilt and bed mesh speeds, `optional` for the board fan and chamber, `available` for the USB event log, and no Box lines.
5. **Install.** `bash ~/plus4-grease/install.sh install`. Expect a backup of `printer.cfg` and `gcode_macro.cfg`, one Klipper restart, and `speed = 300` under `[z_tilt]` and `[bed_mesh]`.
6. **A print.** Any print. Then `grep "Mesh Bed Leveling Complete" ~/printer_data/logs/klippy.log | tail -3` to show the mesh finished, and `python3 ~/plus4-grease/tools/klipper_report.py`.
7. **Z tilt by hand,** since 1.6.0's print start doesn't run it: `G28`, then `Z_TILT_ADJUST` in the console, then `grep -E "Retries:|Making the following Z adjustments" ~/printer_data/logs/klippy.log | tail -4`. Also worth knowing: does the touchscreen's bed leveling run Z tilt? If it does, `Making the following Z adjustments` shows up after it.
8. **Status and uninstall.** `bash ~/plus4-grease/install.sh status` should start with "Firmware V1.6.0 (recorded at install)" and show the three changes `applied`. Then `bash ~/plus4-grease/install.sh uninstall`, `status` again (everything `available`), and `config_diff.py --firmware 1.6.0` (back to only your own changes). Install again afterwards if you want to keep it.
9. **New Fluidd (optional).** Copy `plus4-grease-fluidd-v1.38.1-14.zip` from the release to the printer, `bash ~/plus4-grease/install.sh fluidd install --dry-run`, then without `--dry-run`. Open `http://<printer-ip>:81`. Expect it to connect, temperatures, console, macros and files to work, QIDI's Fluidd settings to be copied, and no Box card. Also say which nginx it is (`nginx -v`). QIDI's page on port 80 should be unchanged.
10. **Opt-ins (optional).** `install --board-fan` and `install --balanced-chamber`. Neither has been installed by Plus4 Grease on any printer yet. For the fan, watch `board_fan` and `mainboard_mcu` in Fluidd during a print; for the chamber, `chamber` and `chamber_probe` with a chamber target.

When something here is done, add a line to [testing.md](testing.md) with the firmware column `V1.6.0`.
