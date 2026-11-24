# Changelog

## 0.14.2
- **Overdrive speaks** (Fluidd build 14): its recorded line plays when a print finishes ("Print complete. Faster than you could have done it..."), Klipper shuts down or a print errors, filament runs out (a pause with no filament at the toolhead), Box drying ends, a Box holding PLA or TPU has cooled, or Plus4 Grease refuses a print or a load while a Box cools. Nothing plays when the page opens. Settings > Theme > Persona voice turns it off. A browser plays sound only while the page is open and after it's been clicked or tapped once.
- The six clips (about 240 KB) are in `fluidd/sounds/overdrive/`, and `tools/build_fluidd.sh` copies them into the page.

## 0.14.1
- **Overdrive's print job card** (Fluidd build 13), as in the persona mockup: while a job is loaded, the status card shows the speed in big numbers with 100%, 140%, 180% and MAX buttons (`M220`; MAX is 220%, which Klipper still holds to the printer's own speed and acceleration limits), the model's thumbnail, a 40-segment progress bar with layer, percent and time left, and elapsed time, flow, filament and height. After a print, while a Box holding PLA or TPU cools, it says the next print won't start yet, with the temperature and minutes left. Fluidd's own status card shows when no job is loaded, and with every other persona setting.
- With a persona on, the side menu shows its labels beside the icons, and the dashboard has a title line: "DASHBOARD" and "EFFICIENCY MODE: ENFORCED".

## 0.14.0
- **Personas in the new Fluidd (build 12)**, starting with **Overdrive**. Settings > Theme > Persona gives the whole page a persona's look and puts a status line in the top bar that says what the printer is doing in the persona's voice. Overdrive: near-black with a red accent, Chakra Petch in spaced capitals, cut-corner cards and buttons, segmented progress bars, its own mark in place of the logo, and lines like "SYSTEM › bracket_v3: 41% done. Layer 112 of 270. Holding the line." or a Box's drying and cool-down. Off goes back to Fluidd's own look. The font is bundled, so it needs no internet. Steward, Sidekick, Serene and Sentinel come next.
- Install with `install.sh fluidd install` and `plus4-grease-fluidd-v1.38.1-12.zip`; your Fluidd settings are kept, and the persona starts Off.

## 0.13.4
- **Fixed in the new Fluidd (build 11): the Box heater target showed "Max 0"** in the temperature card, in red, while `GREASE_BOX_DRY` was drying a Box holding PLA, and the Box card's limit line still said the heater was locked at 0 °C. Both used QIDI's limit alone (PLA and TPU are 0). They now follow `GREASE_BOX_DRY`'s rule: with PLA/TPU drying on, a Box holding PLA or TPU may go up to `pla_max_temp` (45 °C), and to 0 while a print is running or paused. Found on the owner's printer. Install with `install.sh fluidd install` and the new zip, `plus4-grease-fluidd-v1.38.1-11.zip`.

## 0.13.3
- **Fixed: PLA/TPU drying stayed off** even with `variable_pla_drying: True`. The drying file loaded the settings file with `[include plus4-grease-box-dry-setting[s].cfg]`, and QIDI's Klipper reads section names with Python's own rule, which on the printer's Python 3.7 ends a name at its first `]`. Klipper saw a pattern matching no file and used the defaults, so `GREASE_BOX_DRY` refused PLA ("set variable_pla_drying: True..."). Found on the owner's V2.1.1 printer. The include is now `[include plus4-grease-box-dry-setting?.cfg]`; `install` updates an installed drying file from 0.13.0 to 0.13.2. Your settings file isn't touched.
- `tests/test_py37_headers.py` checks that every section and include line Plus4 Grease writes reads the same under Python 3.7's rule. Earlier checks ran on a newer Python, which reads the whole name.

## 0.13.2
- **Fixed: the Box cool-down lock wasn't loaded.** QIDI's Box software rewrites `box.cfg` from its templates through Python's `configparser`, and on the printer's Python 3.7 that cut 0.13.0's include `[include plus4-grease-box-loc[k].cfg]` to `[include plus4-grease-box-loc[k]`, which matches no file. Klipper started normally, but without the lock, and the next `install` called it `skipped`. Found on the owner's V2.1.1 printer right after installing 0.13.1. The include is now `[include plus4-grease-box-loc?.cfg]` after a blank line, with no comment: exactly what that rewrite writes back. The print-start check and drying weren't affected.
- An install with 0.13.0 or 0.13.1's lock shows it as `update`, and `install` (with or without `--box-dry`) replaces it in `box.cfg` and the templates; `uninstall` removes either form.
- Edits can now name the text earlier versions wrote (`older` in `grease/edits.py`), so install updates it and uninstall removes it.
- `tests/test_box_rewrite.py` replays QIDI's rewrite for one to four Boxes and checks Klipper then includes the lock.

## 0.13.1
- **Firmware 1.6.0 is accepted, with its own change list** in a separate file, `grease/edits_v160.py`. 1.6.0 came before the QIDI Box, and its print start, pause and resume differ from 1.8.1 and later, so its edits are written and tested against QIDI's published 1.6.0 files alone (`stock/plus4-1.6.0/`, from `QIDITECH/QIDI_PLUS4` `f2b5caf`) and nothing made for later firmware reaches it. It has the bed mesh save wait, both probe speeds, `--board-fan` and `--balanced-chamber`; the Box runout-flag wait and `--box-dry` aren't offered. The installer says so on 1.6.0, and it hasn't run on a 1.6.0 printer yet: [docs/testing-1.6.0.md](docs/testing-1.6.0.md) is the plan.
- Install records the firmware it read, and `status` (which doesn't ask for `sudo`) and `uninstall` use the change list it recorded.
- `tools/config_diff.py --firmware 1.6.0` compares with QIDI's 1.6.0 files. Without `--firmware` it uses the firmware install recorded, else V2.1.1, as before.
- `docs/plus4-notes.md` has a [Firmware 1.6.0](docs/plus4-notes.md#firmware-160) section: what differs from V2.1.1, and what 1.6.0's Klipper and Moonraker have.

## 0.13.0
- **PLA and TPU can be dried in the Box**, with `install --box-dry-pla` (or `variable_pla_drying: True` in the new settings file). QIDI's limit for them is 0 because the Box's feed tubes run along its floor beside the heaters, where PLA or TPU softens and can jam if it's loaded warm. `GREASE_BOX_DRY` now dries a Box holding them up to 45 °C (`pla_max_temp`, at most 50), never during a print and never with that Box's filament in the toolhead. See the README's [Drying PLA and TPU in the Box](README.md#drying-pla-and-tpu-in-the-box).
- **A cool-down lock** comes with `--box-dry`, whether PLA/TPU drying is on or not: after a Box's heater has run, for whatever reason, PLA and TPU from that Box don't load until its air is at or below `unlock_temp` (35 °C) and `cool_minutes` (30) have passed. `plus4-grease-box-lock.cfg` puts it in front of QIDI's `E_LOAD`, `E_BOX` and `EXTRUDER_LOAD`, which it refuses; it never waits, since a print paused for half an hour would be spoiled. Install adds its include to `box.cfg` and to QIDI's root-owned Box templates `/home/mks/cfg_with_1` to `cfg_with_4` (with `sudo`, keeping their owner and mode), and leaves it out if Klipper lacks one of those commands or the printer has no Box.
- **A print-start check** with `--box-dry`: `_GREASE_BOX_PRINT_CHECK` runs first in `PRINT_START`, before anything heats, and doesn't start the print while a Box holding PLA or TPU is drying or cooling, saying which Box and how long. A Box without PLA or TPU dries during a print as before; to dry one during a print, take its PLA and TPU out.
- **Settings** in `plus4-grease-box-dry-settings.cfg`: `pla_drying`, `pla_max_temp`, `unlock_temp`, `cool_minutes`, each held to a safe range. Written once, never overwritten; `uninstall` removes it only if it's unchanged. `GREASE_BOX_DRY_SETTINGS` shows the values in use, and `status` shows whether PLA/TPU drying is on.
- An install with `--box-dry` from 0.9.1 to 0.12.0 is updated by a plain `install`, and gets the lock, the print-start check and the settings file without the switch again.
- The new Fluidd (build 10): the Box card dries PLA and TPU when that's on, shows a Box's cool-down (temperature, unlock temperature, minutes left), and turns Load and Eject off for a locked PLA or TPU slot.
- The installer can edit files in the home folder that only root can write (QIDI's Box templates), backing them up and putting them back like the config files. A failed write puts back only what was already written.
- QIDI's stock Box templates `cfg_with_0` to `cfg_with_4` are in `stock/plus4-2.1.1/`, and the tests install against a printer with one Box.

## 0.12.0
- Firmware 1.8.1 and 1.8.2 are accepted, for `install` and `fluidd install`, with a line saying they're untested. QIDI sent them only as online updates, so their files can't be checked. QIDI's published 1.7.1 configs before them have the same stock text as V2.1.1 wherever Plus4 Grease edits, so the edits should apply the same way on 1.8.x; [docs/plus4-notes.md](docs/plus4-notes.md#firmware-18x) has the comparison.
- QIDI's stock 1.7.1 `printer.cfg`, `gcode_macro.cfg` and filament list are in `stock/plus4-1.7.1/`. Tests check that every change applies and reverts on them, and that every filament 1.7.1 lists has the same Box drying limit as in V2.1.1.
- Corrected: NOTICE.md gave QIDI's Plus 4 repository as GPL v3; it's AGPL v3. NOTICE.md also now names the stock files in `stock/`.
- The firmware version is read the same whether QIDI writes `V1.8.1`, `v1.8.1` or `1.8.1`.

## 0.11.0
- Up to four Boxes: the Box card's slots, layout, climate, heater limits and drying, and the drying macros, each tested with one to four Boxes.
- Box card (Fluidd build 9), with commands QIDI's touchscreen uses on V2.1.1, from qbdisplay's notes:
  - **Retry** under a failed Box step or a Box warning sends `TRY_MOVE_AGAIN`, as the touchscreen's Retry after a Box error does.
  - **Box self-check** in Box settings sends `BOX_SELF_INSPECTION`; off while printing, while paused, or while the Box is busy.
  - Drying started on the touchscreen (QIDI's `ENABLE_BOX_DRY`, read from `box_extras.boxes[].dry_state`) shows on the card with its temperature and a **Stop** that sends `DISABLE_BOX_DRY BOX=N`, with or without `--box-dry`. Its time left isn't shown: QIDI's end time is in Klipper's clock, which the page doesn't have.

## 0.10.0
- Corrected: QIDI's touchscreen dries the Box with QIDI's own `ENABLE_BOX_DRY BOX=1 TEMP=<°C> END_TIME=<hours>` / `DISABLE_BOX_DRY BOX=1` (a timer kept by QIDI's Box module, no humidity control), not by setting the heater directly as 0.9.0's notes said. `GREASE_BOX_DRY` is unchanged. Found in qbdisplay's notes and confirmed in QIDI's `box_extras.so`.
- The new Fluidd's Box card has **Edit filament** (the pencil beside a slot's label; Fluidd build 8): pick the slot's vendor, filament and color from QIDI's filament list for any spool, with or without an RFID tag. It saves them as QIDI's own page and touchscreen do on V2.1.1: `SAVE_VARIABLE VARIABLE=vendor_slotN VALUE="<ID>"`, then `filament_slotN` and `color_slotN`, slot 16 being the external spool. Off while the Box or a print is busy and for an empty Box slot. From Valve Oil's Fluidd.
- `docs/plus4-notes.md` says how the Plus 4's Box reads spool tags, and why Valve Oil's Box firmware that reads other brands' tags doesn't fit the Plus 4's Box as it is.

## 0.9.1
- Box drying works: 0.9.0's macros were named `PLUS4_BOX_DRY` and `PLUS4_BOX_DRY_STOP`, and Klipper reads a command name only up to its first run of digits, so it took them as a command called `PLUS4` and never ran them. They're now `GREASE_BOX_DRY` and `GREASE_BOX_DRY_STOP` (Fluidd build 7 sends those). `tests/test_box_dry.py` now splits every command the way Klipper does and fails on a name Klipper would cut short.
- `install` updates a file an earlier Plus4 Grease version wrote for a change (recognized by its SHA-256), without the change's switch again; `status` shows it as `update`. 0.9.0's `plus4-grease-box-dry.cfg` is updated this way.

## 0.9.0
- Optional `install --box-dry`: Box drying with a timer and humidity control, kept by Klipper so it carries on with the web page closed. (Its macro names didn't work; fixed in 0.9.1.) `PLUS4_BOX_DRY BOX=1 TEMP=45 HOURS=4 HUMIDITY=20` sets the Box heater (`SET_HEATER_TEMPERATURE HEATER=heater_box1`), stops after the hours given (0 runs until stopped), and with `HUMIDITY` switches the heater off at or below that humidity and back on 5 points above it. `PLUS4_BOX_DRY_STOP BOX=1` stops it. It never goes above QIDI's Box limit for the filaments loaded (a table from QIDI's V2.1.1 `officiall_filas_list.cfg`; 0 for PLA and TPU refuses to heat), refuses a loaded filament that table doesn't have, and stops if the Box heater is changed elsewhere. The macros are in `plus4-grease-box-dry.cfg`, included from `printer.cfg`; `uninstall` removes both.
- The new Fluidd's Box card has drying controls when `--box-dry` is installed: temperature, hours and humidity, Dry and Stop, and what's running (Fluidd build 6).
- `tests/test_box_dry.py` renders the drying macros as Klipper does (Jinja2) against a pretend Plus 4 and checks the limits, timer, humidity switching and hand-over.

## 0.8.0
- The new Fluidd holds the Box heater to QIDI's limit (Fluidd build 5). QIDI lets a Box heater go no higher than the lowest Box limit of the filaments loaded in that Box, from `officiall_filas_list.cfg`: 0 for PLA and TPU, which locks it, 45 °C for PETG and ABS, up to 65 °C for nylons. Build 4 let `heater_box1` be set up to its `target_max_temp` (90 °C) whatever was loaded. The temperature card now refuses a higher target and greys out a locked Box heater, and the Box card says what the limit is. QIDI's own page checks only the Box's first slot; this checks every loaded slot. From Valve Oil's Fluidd.
- Heaters with QIDI's `target_min_temp` and `target_max_temp` (the stock chamber's 45-65 °C) show those limits in the temperature card instead of failing in Klipper.
- Box settings on the Box card: Detection on insertion, Detection on startup and Automatic reload, set as QIDI's own page sets them (`SAVE_VARIABLE VARIABLE=<name> VALUE="1"` or `"0"`).

## 0.7.1
- The Box card draws loaded filament past the hub to the toolhead, extruder and nozzle on the Plus 4 (Fluidd build 4). It looked for the filament switch QIDI's newer printers have at the toolhead; the Plus 4's toolhead sensor is `hall_filament_width_sensor`, which now counts as filament while its diameter reading is above its `min_diameter`, as QIDI's own runout check does. The same reading finds the external spool loaded.

## 0.7.0
- The new Fluidd's Box card has Load, Unload, Eject and Read RFID for the selected slot (Fluidd build 3). They send exactly what QIDI's own Fluidd sends on V2.1.1: `E_LOAD slot=N`, `E_UNLOAD slot=N`, `E_BOX slot=N` and `RFID_READ SLOT=slotN`. Valve Oil's commands for QIDI's newer firmware are never sent. The buttons are off while printing, while the Box is busy or Klipper isn't ready, and until Klipper answers the last Box command; Load is off for the slot that's loaded and Unload for every other slot.

## 0.6.0
- The new Fluidd has a QIDI Box card (Plus4 Grease build 2 of Fluidd v1.38.1). It shows each slot's filament, color and RFID state, the Box's humidity and temperature, which slot is loaded, the hub and toolhead sensors, tool mapping, auto-reload groups, and a running or failed Box step with QIDI's error. It's read-only: load, unload and drying stay on the touchscreen and QIDI's page. Ported from Valve Oil's Fluidd; see `fluidd/README.md`.
- `install.sh fluidd install` updates an installed earlier build in place and keeps its settings; `status` says when an update is waiting.
- The Fluidd changes live in `fluidd/plus4-grease.patch`, applied by `tools/build_fluidd.sh`.

## 0.5.0
- Optional `fluidd install`: upstream Fluidd v1.38.1 on port 81, beside QIDI's Fluidd v1.30.4, which stays untouched on port 80. It's served by the printer's own nginx from `~/plus4-grease-fluidd` through its own site file. Every text file ships with a `.gz` copy that nginx sends as stored (`gzip_static`; on an nginx without it, the site compresses as it sends instead), hashed assets are cached by the browser for a year, and the site writes no access log. A first visit downloads about 4.4 MB.
- The new Fluidd keeps its settings in its own Moonraker namespace, `plus4_grease_fluidd`; the first install copies QIDI Fluidd's settings in. Cameras are passed to QIDI's own site, so they work the same on both pages.
- Install checks the bundle's SHA-256 and the port, has `nginx -t` test the site, reloads nginx, and checks that the page loads and reaches Moonraker; any failure puts everything back as it was, including an earlier version on an upgrade. `fluidd remove` deletes the site and the folder and keeps the settings.
- New `tools/build_fluidd.sh` builds the bundle from Fluidd's own source on a computer.
- `status` lists the new Fluidd too; `uninstall` reminds you it's still there.

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
