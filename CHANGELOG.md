# Changelog

## 0.4.0
- Optional `install --board-fan`: QIDI's `[controller_fan board_fan]` is replaced by `plus4-grease-board-fan.cfg`, a fan driven by the X/Y TMC2240 driver temperatures (60-70 °C) and the mainboard chip (45-65 °C, new `[temperature_sensor mainboard_mcu]`), with a 30% floor while X/Y are enabled or the chamber is heating and full speed on shutdown. From JarvisAKF's Plus 4.
- Optional `install --balanced-chamber`: the chamber heater follows the mean of the toolhead chip (`GD32`, counted three times) and QIDI's chamber thermistor (now `[temperature_sensor chamber_probe]`), with `max_power` 0.6, `max_temp` 80 °C and a 70 °C sensor-deviation limit; QIDI's 45-65 °C target range and bed assist are dropped. QIDI's `Chamber_Thermal_Protection_Sensor` (140 °C) is left as it is. From JarvisAKF's Plus 4.
- Plus4 Grease can now create a file in the config folder for a change and remove it on uninstall; a Klipper start failure removes it with the rest. A change that finds someone else's file there is left alone.
- A stock block only counts where it starts a line, so a block whose first line was commented out (`#[controller_fan board_fan]`) is left alone.
- New `tools/config_diff.py`: compares a printer's config with QIDI's stock V2.1.1 files, section by section, with Plus4 Grease's own edits taken out first and serial numbers hidden. The stock files now live in `stock/plus4-2.1.1/`, and the tests use them. An option Klipper's SAVE_CONFIG moved into the SAVE_CONFIG block (a re-tuned PID, say) shows as moved, with both values.
- README: what Plus4 Grease is, how it differs from stock QIDI, and how the same Plus4 Grease works on stock and Beacon-converted printers, with what a Beacon conversion was seen to change.

## 0.3.0
- USB event log: a udev rule and a small root-owned script add a line to `~/printer_data/logs/plus4-grease-usb.log` each time a USB device connects or disconnects (time, port, IDs, and on connect the device's name; never its serial number), synced to the eMMC and capped at about 2000 lines. The Plus 4's Linux logs live in RAM and are lost when the printer is switched off. Install writes the two files with `sudo`; uninstall removes them and leaves the log.
- `tools/klipper_report.py` lists the last USB events and, for each shutdown, the USB events around it. A "Lost communication" with a USB board right after Linux saw it disconnect is put down to the board being switched off, unplugged, losing power or resetting; with the log running and no disconnect, to the board itself stopping.
- New `tools/klipper_report.py`: streams through `klippy.log` (a few MB of memory, low CPU priority) and reports each board's chip, motors and microsteps, how loaded the boards, their serial links and the mainboard's Linux processor were during the last print, and for each shutdown what Klipper's statistics just before it point to. Read-only.

## 0.2.0
- Z tilt and bed mesh travel between probe points at 300 mm/s instead of QIDI's 150, by changing `speed:` under `[z_tilt]` and `[bed_mesh]` in `printer.cfg` where it's still QIDI's 150. A full 9×9 mesh spends about 8 s less moving. Measured first with `tools/speed_test.py`: a Plus 4 ran X/Y up to 500 mm/s at 20000 mm/s² over the probing area with no lost steps. Uninstall puts 150 back.
- `install --replace-own-speeds` also sets those two speeds where you've set them yourself (or left them out), and uninstall puts yours back. Without it, a skipped speed change says what your `printer.cfg` has. After installing, Plus4 Grease checks that Klipper loaded the new speeds and says so if another config file sets them again.
- `tools/speed_test.py` stays inside the area probing uses, shifted by the probe's offset, and never enters QIDI's no-print zones (X over 292 or Y over 301). It checks homing alone first, and counts a drift of 2 full steps or more as lost steps, since sensorless homing can land a full step either way and a slipping motor jumps 4 full steps at a time.

## 0.1.0
- First release, for the QIDI Plus 4 on firmware V2.1.1.
- Installer with `install`, `install --dry-run`, `status`, and `uninstall`. It checks the printer is a Plus 4 on V2.1.1, backs up every file it changes, restarts Klipper, and puts everything back if Klipper doesn't come back ready.
- Print start no longer waits 1.6 s while clearing the Box runout flags.
- A new bed mesh is saved after 0.5 s instead of 5 s.
