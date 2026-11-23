# Plus4 Grease

Small, reversible improvements and diagnostic tools for the **QIDI Plus 4** on QIDI firmware **V2.1.1**, stock or converted to a Beacon probe. Firmware 1.8.1 and 1.8.2 are accepted too, but not tested yet; see [On firmware 1.8.1 and 1.8.2](#on-firmware-181-and-182). Firmware 1.6.0, from before the QIDI Box, has a separate, smaller change list; see [On firmware 1.6.0](#on-firmware-160).

> [!IMPORTANT]
> Plus4 Grease is an unofficial, independent project. It is not made or supported by QIDI, and it is **not Valve Oil**. Valve Oil's author doesn't support the Plus 4, so please don't take Plus4 Grease problems to the Valve Oil Discord or issue tracker. Open an issue here instead.

> [!CAUTION]
> Watch the first print after installing, and be ready to stop the printer. You use this at your own risk.

## What Plus4 Grease is

Plus4 Grease is an add-on for QIDI's own software on the Plus 4. It keeps QIDI's firmware, Klipper, Moonraker, Fluidd, touchscreen and Box software as they are, and makes a few small edits to QIDI's Klipper config where QIDI's settings cost time for nothing. Each edit is checked against QIDI's original text before it's made, the file is backed up first, and `uninstall` undoes it.

If you want it, it also adds a current Fluidd on its own port next to QIDI's, which stays where it is (see [A current Fluidd beside QIDI's](#a-current-fluidd-beside-qidis)).

It also brings read-only tools for finding out what a Plus 4 is doing: a speed test, a Klipper report that explains shutdowns like "Timer too close" and "Lost communication", and a comparison of your config with QIDI's stock one.

The ideas come from [Valve Oil](https://github.com/thelegendtubaguy/valve-oil), which does this for QIDI's Max 4, Plus 5 and Smart 5. Plus4 Grease is a separate project, written for the Plus 4's older software: Klipper on Python 3.7, Debian 10, and the `mks` user. This is version 0.13.

## Plus4 Grease vs stock QIDI

| | Stock QIDI V2.1.1 | With Plus4 Grease |
|---|---|---|
| Clearing the Box runout flags at print start | 16 flags with a 0.1 s wait after each: 1.6 s | no waits; each save already finishes before the next command runs |
| Saving a new bed mesh (`G29`) | a fixed 5 s wait first | 0.5 s, as Valve Oil does on the Max 4 and Plus 5 |
| Z tilt: travel between probe points | 150 mm/s | 300 mm/s; each 255 mm trip takes about 0.9 s instead of 1.7 s |
| Bed mesh: travel between probe points | 150 mm/s | 300 mm/s; a full 9×9 mesh spends about 8 s less moving |
| USB devices connecting and disconnecting | only in Linux's log, which the Plus 4 keeps in RAM and loses when switched off | also in `~/printer_data/logs/plus4-grease-usb.log` on the eMMC, without serial numbers |
| When Klipper stops ("Timer too close", "Lost communication") | QIDI's generic message | `tools/klipper_report.py` says what the numbers just before it point to and matches USB events, so a Box rebooted by a power flicker shows as one |
| Board fan (optional, `--board-fan`) | full speed whenever X/Y are enabled or the chamber heater is on | follows the hottest of the X/Y drivers and the mainboard chip, 30% floor while busy, full speed if Klipper shuts down |
| Chamber temperature (optional, `--balanced-chamber`) | the heater follows one thermistor | the heater follows an average of the toolhead chip and that thermistor; see [Optional changes](#optional-changes) |
| Box drying (optional, `--box-dry`) | a timer on the touchscreen | a timer and humidity control, from the console or the new Fluidd's Box card |
| PLA and TPU in the Box (optional, `--box-dry-pla`) | can't be dried in the Box at all | dried up to 45 °C while nothing prints; then PLA and TPU don't load from that Box, and no print starts, until it has cooled; see [Drying PLA and TPU in the Box](#drying-pla-and-tpu-in-the-box) |
| Web page (optional, `fluidd install`) | QIDI's Fluidd v1.30.4 on port 80, with QIDI's Box panel | QIDI's stays on port 80, untouched; Fluidd v1.38.1 is added on port 81 with a Box card, sent pre-compressed (a first visit downloads about 4.4 MB and the printer compresses nothing) |
| Firmware, Klipper, Moonraker, QIDI's Fluidd, touchscreen, Box software | QIDI's | unchanged |

Probing itself is unchanged; only the travel between points is faster. The Plus 4's X/Y motors are open-loop, and Valve Oil's Plus 5 lost position at 565 mm/s, so the speed was measured first: on a tested Plus 4, `tools/speed_test.py` ran X/Y up to 500 mm/s at the full 20000 mm/s² over the probing area with no lost steps. 300 leaves room for printers that haven't been tested, and faster would save under 2 s more per full mesh.

## Stock and Beacon Plus 4s

There is one Plus4 Grease for both. Each change looks for QIDI's exact stock text and works from what it finds, so on a printer converted to a Beacon probe it applies what still fits and leaves the conversion's own changes alone.

| Change | Stock Plus 4 | Beacon conversion |
|---|---|---|
| Print start without the runout-flag waits | applies | applies where the conversion left `PRINT_START`'s flag loop as QIDI wrote it |
| Bed mesh save after 0.5 s | applies | skipped: the conversion's `G29` is its own |
| Z tilt and bed mesh at 300 mm/s | applies | a conversion usually sets its own speeds, so these are skipped unless you run `install --replace-own-speeds`, which sets them to 300 too and keeps a note of yours for `uninstall`. With a Beacon, the bed mesh speed is also its scan speed. |
| USB event log and the tools | applies | applies |
| `--board-fan`, `--balanced-chamber` | apply when asked | apply when asked, where the conversion left QIDI's board fan or chamber heater as QIDI wrote them |
| `--box-dry` | applies when asked | applies when asked; its print-start check goes where the conversion left the start of QIDI's `PRINT_START` as QIDI wrote it |

What one Beacon conversion was seen to change, as `tools/config_diff.py` showed it (conversions differ; check yours the same way):

- Its `G29` finds Z zero by touching the bed (Beacon Contact), scans the mesh with `BED_MESH_CALIBRATE RUNS=2`, and never calls QIDI's `SAVE_CONFIG_QD`, so the save-wait change has nothing to shorten. It also sets acceleration to 1000 mm/s² while meshing, so the 300 mm/s mesh speed is only reached on long scan moves.
- It removes QIDI's probe (`[smart_effector]`, `[qdprobe]`), QIDI's `[homing_override]`, and the probe's Z-offset macros, which it replaces with Beacon's. Plus4 Grease touches none of these.
- It sets its own Z tilt (200 mm/s, 5 retries, 0.008 mm tolerance) and a finer bed mesh (14×14), which is why the speed changes need `--replace-own-speeds` there.

`install --dry-run` shows which changes apply on your printer before anything is touched. So far Plus4 Grease has been tested on a Beacon-converted Plus 4 with one Box; see [docs/testing.md](docs/testing.md). Results from a stock Plus 4 are wanted, especially for the bed mesh save change and the 300 mm/s probe travel with QIDI's own probe. `tools/config_diff.py` lists everything a printer's config changes from QIDI's stock one, which is a quick way to see what a conversion touched.

## Optional changes

Three changes are off unless you ask for them, because they change how a fan and heaters are controlled. The first two come from [JarvisAKF](https://github.com/JarvisAKF)'s own Plus 4, where they've run for over a year. Add the switches to `install` (and to `install --dry-run` to see them first); `uninstall` takes them out with everything else.

**`--board-fan`: a temperature-driven board fan.** QIDI's `[controller_fan board_fan]` runs the mainboard fan at full speed whenever X/Y are enabled or the chamber heater is on. This replaces it with `plus4-grease-board-fan.cfg`: every 5 s the fan is set from the hottest of the X/Y TMC2240 drivers (ramping from 60 to 70 °C) and the mainboard's own chip (45 to 65 °C, a new `[temperature_sensor mainboard_mcu]`), with a 30% floor while X/Y are enabled or the chamber is heating, and full speed if Klipper shuts down. QIDI's `GD32` sensor isn't used for this: it reads the toolhead board's chip, not the mainboard's.

**`--balanced-chamber`: a chamber reading that isn't one thermistor.** QIDI's chamber heater follows a single thermistor. With this, it follows the mean of the toolhead board's chip temperature (`GD32`, counted three times) and that thermistor (now `[temperature_sensor chamber_probe]`, counted once), so the reading reflects the toolhead as well as the air at that one thermistor. It also:

- raises `max_power` from 0.4 to 0.6 and `max_temp` from 70 to 80 °C, an overshoot buffer: a 65 °C target can read 70–72 °C on the way;
- drops QIDI's 45–65 °C range for chamber targets and QIDI's raising of the bed to chamber + 25 °C when the chamber heats.

Klipper shuts the printer down if the mean passes 80 °C or the sensors disagree by more than 70 °C, which catches a thermistor that fails open or shorted. QIDI's own `Chamber_Thermal_Protection_Sensor` at the heater is left as it is and still shuts the printer down at 140 °C. PID values are QIDI's; run `PID_CALIBRATE HEATER=chamber TARGET=60` afterwards if the chamber overshoots more than you like.

**`--box-dry`: Box drying with a timer and humidity control.** QIDI's touchscreen dries the Box with QIDI's own `ENABLE_BOX_DRY BOX=1 TEMP=<°C> END_TIME=<hours>` (and `DISABLE_BOX_DRY BOX=1`), a timer with no humidity control. This adds two macros with a timer and humidity control, which the new Fluidd's Box card uses: `GREASE_BOX_DRY BOX=1 TEMP=45 HOURS=4 HUMIDITY=20` and `GREASE_BOX_DRY_STOP BOX=1`. HOURS 0 runs until stopped. With HUMIDITY, the heater goes off once the Box reads at or below it and back on 5 points above it, until the time runs out. It never heats above QIDI's Box limit for the filaments loaded in that Box (from QIDI's filament list: 45 °C for PETG, ABS and ASA; up to 65 °C for nylons and other carbon-fiber blends; 0 for PLA and TPU, see below), refuses a loaded filament that isn't in QIDI's list, and stops if the Box heater is changed elsewhere, from the touchscreen say. A Klipper restart ends it with the heater off. It also adds the cool-down lock described next, which guards PLA and TPU whatever heated the Box.

### Drying PLA and TPU in the Box

**Why QIDI won't do it.** QIDI's filament list gives PLA and TPU a Box limit of 0 °C, so the touchscreen, QIDI's page and Plus4 Grease all refuse to heat a Box with PLA or TPU in it. The limit is per Box: with two Boxes, the one without PLA dries and the one with a single roll of PLA doesn't. The reason, from [JarvisAKF](https://github.com/JarvisAKF), who runs this printer: the Box's feed tubes run along the inside of its floor, right beside the heaters. Any PLA or TPU sitting in those tubes gets much hotter than the air the Box's sensor reads, softens, and if it's loaded before it hardens again it can jam inside a tube. So switching the drying off just before a print isn't enough: the tubes need about half an hour to cool. Many owners would still like to dry PLA in the Box.

**What Plus4 Grease does instead.** With PLA/TPU drying turned on, a Box holding PLA or TPU can be dried while nothing is printing, and then that Box is locked for loading PLA and TPU until it has cooled. Nothing ever waits for a Box partway through a print: a print sitting still for half an hour would be spoiled. So the rules keep a print from needing a Box that's drying or cooling:

1. **Drying.** `GREASE_BOX_DRY` (or Dry on the new Fluidd's Box card) heats a Box holding PLA or TPU up to 45 °C, with the same timer and humidity control. A higher limit filament beside it (ASA, say) is held to that too. It refuses while a print is running or paused, and while that Box's filament is in the toolhead (QIDI's last loaded slot is in that Box and the toolhead sensor sees filament), so nothing is pulled through or fed from warm tubes. Unload first; filament from the external spool doesn't count.
2. **The lock.** Once its heater stops, the Box stays locked for loading PLA and TPU until both are true: its air is at or below 35 °C, and 30 minutes have passed since its heater last ran. The time is there because the tubes beside the heaters cool more slowly than the air the sensor reads.
3. **What's locked.** QIDI's page, the touchscreen and the new Fluidd load a slot with QIDI's `E_LOAD` and eject it with `E_BOX`; the tool changes `T0` to `T15` and QIDI's own Box steps load with `EXTRUDER_LOAD`. The lock sits in front of all three and refuses a locked load with a message saying how warm the Box is and how long is left. The new Fluidd's Box card turns Load and Eject off for that slot and shows the cool-down.
4. **Print start.** The first thing `PRINT_START` does, before anything heats, is check each Box holding PLA or TPU. If one is drying or still cooling, the print doesn't start, and the message says which Box and how long it has left. Start the print again once it has cooled, or take the PLA and TPU out of that Box.
5. **Drying during a print.** A Box with no PLA or TPU in it dries during a print as before, ASA say, and the print can use it. To dry a Box during a print, take any PLA or TPU out of it first (eject it, or pull the spool): a Box holding both ASA and PLA isn't dried while printing.

The lock applies whatever heated the Box: Plus4 Grease's drying, the touchscreen's, or the Box heater set by hand. Drying ASA and then putting a roll of PLA in while the Box is still warm locks that PLA too. It's part of `--box-dry` even with PLA/TPU drying off, and so is the print-start check. ASA, PETG, ABS and nylons keep QIDI's limits and are never locked. A filament QIDI's list doesn't name isn't locked either, but it can't be dried until it's set on the touchscreen. After a Klipper restart, a Box more than 5 °C above the unlock temperature counts as just heated, and the lock starts over. A Box that's only a little warm, as in a warm room, doesn't lock anything.

**Turning it on.** `bash ~/plus4-grease/install.sh install --box-dry-pla` installs `--box-dry` with PLA/TPU drying on. Already installed? Run the same command: it switches the setting on. Or change it yourself (below) and restart Klipper.

**Settings.** They're in `~/printer_data/config/plus4-grease-box-dry-settings.cfg`. Edit it in Fluidd's config editor, then Save & Restart. Plus4 Grease writes it once and never overwrites it, and `uninstall` leaves it in place once you've changed it. `GREASE_BOX_DRY_SETTINGS` in the console shows the values in use.

| Setting | Default | Range | What it does |
|---|---|---|---|
| `variable_pla_drying` | `False` | `True` or `False` | Dry PLA and TPU in the Box |
| `variable_pla_max_temp` | `45` | 35 to 50 °C | The highest drying temperature for a Box holding PLA or TPU |
| `variable_unlock_temp` | `35` | 30 to 45 °C | PLA and TPU load once the Box's air is at or below this... |
| `variable_cool_minutes` | `30` | 10 to 120 | ...and this many minutes have passed since its heater last ran |

A value outside its range is treated as the nearest end of it. Klipper reads these as Python values, so `True` and `False` keep their capital letters; Klipper won't start otherwise, and its error names the line.

**Good to know.**

- In a room warmer than the unlock temperature, a Box that has been heated can't unlock. Raise `unlock_temp`.
- The print-start check looks at every Box holding PLA or TPU, not only the ones a print will use, since a print's later tool changes aren't known when it starts. With two Boxes, PLA cooling in Box 1 keeps a print from Box 2 from starting until it's done.
- The lock is `plus4-grease-box-lock.cfg`, which `box.cfg` includes. QIDI makes `box.cfg` from its Box templates (`/home/mks/cfg_with_1` to `cfg_with_4`) when the number of Boxes it finds changes, so install adds the include line to those as well. They belong to root, so install writes them with `sudo`, keeping their owner and mode, and `uninstall` puts them back. A printer with no Box connected skips the lock; install again after connecting one. Install also checks that Klipper has QIDI's `E_LOAD`, `E_BOX` and `EXTRUDER_LOAD`, and leaves the lock out if one is missing, since Klipper won't start without them.

## A current Fluidd beside QIDI's

QIDI's web page is Fluidd v1.30.4 with QIDI's Box panel added. `fluidd install` adds upstream Fluidd v1.38.1 next to it, on port 81, and leaves QIDI's exactly as it is on port 80. Open whichever you like: `http://<printer-ip>/` is QIDI's, `http://<printer-ip>:81/` is the new one. (Port 8080 is taken by the camera.)

- **What's different:** eight Fluidd versions of fixes and features since QIDI's copy. It's also lighter on the printer: every file comes pre-compressed and nginx sends it as stored, the browser keeps the hashed files for good, and this page writes no nginx access log. The whole folder is 17 MB.
- **The Box:** a Box card, ported from Valve Oil's Fluidd, shows each slot's filament and color, the Box's humidity and temperature, which slot is loaded, the hub and toolhead sensors, and a running or failed Box step with QIDI's error. Its Load, Unload, Eject, Read RFID, Edit filament (set any spool's filament and color by hand), Box settings, Box self-check and Retry after a Box error send the same commands as QIDI's own page or touchscreen. Drying started on the touchscreen shows there with a Stop button. The Box heater is held to QIDI's limit for the filaments loaded (locked for PLA and TPU), as on QIDI's page. With `install --box-dry` it can also dry the Box with a timer and humidity control (see [Optional changes](#optional-changes)), dry PLA and TPU when that's turned on, and show a Box's cool-down, with Load and Eject off for its PLA and TPU until it has cooled ([Drying PLA and TPU in the Box](#drying-pla-and-tpu-in-the-box)).
- **Settings:** it keeps its own (Moonraker namespace `plus4_grease_fluidd`), so the two pages never overwrite each other's layout. The first install copies QIDI Fluidd's settings across, so your theme, macros and layout carry over.
- **Cameras** are passed through to QIDI's page, so the new one uses the same camera setup.

**Install.** Get `plus4-grease-fluidd-v1.38.1-10.zip` onto the printer next to `install.sh` or in your home folder. It's attached to the [latest release](https://github.com/JarvisAKF/Plus4-Grease/releases/latest), or build it with `tools/build_fluidd.sh` on a computer. From your computer (PowerShell, in the folder with the zip):
```
scp plus4-grease-fluidd-v1.38.1-10.zip mks@<printer-ip>:~/
```
Then on the printer:
```
bash ~/plus4-grease/install.sh fluidd install --dry-run
bash ~/plus4-grease/install.sh fluidd install
```
It checks the zip's SHA-256, unpacks it to `~/plus4-grease-fluidd`, adds the nginx site `/etc/nginx/sites-available/plus4-grease-fluidd` with `sudo`, has nginx test the site, reloads nginx (QIDI's page and a running print aren't interrupted), and checks the new page loads and reaches Moonraker. If any step fails, it puts everything back. `--port` picks another port. Running it again after updating Plus4 Grease updates an installed Fluidd in place and keeps its settings.

**Remove:** `bash ~/plus4-grease/install.sh fluidd remove` deletes the site and the folder and reloads nginx. Its settings stay in Moonraker's database, so a reinstall picks them up.

## How it stays safe

- **It only edits QIDI's stock text.** Each change looks for QIDI's exact lines from V2.1.1 (the same lines are in QIDI's 1.7.1 configs; on 1.6.0, its own list looks for 1.6.0's) and applies only where it finds them, once, at the start of a line (so a line you've commented out doesn't count). If you've changed that part yourself, for example with a Beacon probe conversion, that change is skipped and your file is left as it is. The one exception is the probe speeds, and only when you ask with `--replace-own-speeds`. After the restart, install checks that Klipper really loaded the new speeds, since another included file can set them again.
- **Backups first.** Every file it changes is copied to `~/.plus4-grease/backups/` first.
- **Klipper has to start.** After a change it restarts Klipper. If Klipper doesn't come back ready, it puts your files back by itself.
- **Clean uninstall.** `uninstall` puts QIDI's lines back.
- **Few system files.** Outside Klipper's config there's only the USB event log: a udev rule in `/etc/udev/rules.d/99-plus4-grease-usb.rules` and its script in `/usr/local/lib/plus4-grease/`, written with `sudo` and owned by root, since udev runs the script as root. `uninstall` removes both and leaves the log. If you add the new Fluidd, its nginx site file joins them; `fluidd remove` takes it out. `--box-dry` adds one line to QIDI's Box templates in `/home/mks`, which are root's; `uninstall` takes it out.
- **Your settings stay yours.** The Box drying settings file is written once and never overwritten. `uninstall` removes it only if you never changed it.
- **It checks the printer.** It runs only on a Plus 4 (`/dev_info.txt` reads `QIDI@x-plus_4`) on firmware V2.1.1, 1.8.2, 1.8.1 or 1.6.0, as the `mks` user, and never while a print is running or paused.

## Install

You need SSH access to the printer as `mks`. QIDI's default password is `makerbase`.

**1. Get Plus4 Grease onto the printer.** Either:

- On the printer, if it can reach the internet:
  ```
  git clone https://github.com/JarvisAKF/Plus4-Grease ~/plus4-grease
  ```
- Or from your computer: download the source zip from the [latest release](https://github.com/JarvisAKF/Plus4-Grease/releases/latest), unpack it, rename the folder to `plus4-grease`, and copy it over (in PowerShell on Windows, from the folder that holds it):
  ```
  scp -r plus4-grease mks@<printer-ip>:~/
  ```

> [!NOTE]
> **LAN Only mode cuts the Plus 4 off from the internet.** On the Plus 4, QIDI's touchscreen LAN mode adds firewall rules that block every reply from outside your home network, so downloads on the printer time out. Turn LAN mode off on the touchscreen for the download, or copy the files from your computer instead.

**2. See what it would change.** On the printer:
```
bash ~/plus4-grease/install.sh install --dry-run
```
It asks for the `mks` password once, to read QIDI's firmware version, which is only readable with `sudo`. Each change is listed as `available`, `applied`, or `skipped`, and a skipped speed change says what your `printer.cfg` has instead.

**3. Install:**
```
bash ~/plus4-grease/install.sh install
```
Klipper restarts, so the printer ends up unhomed.

## Other commands

```
bash ~/plus4-grease/install.sh status      # what's applied
bash ~/plus4-grease/install.sh uninstall   # put QIDI's lines back
bash ~/plus4-grease/install.sh fluidd status
```

**After a QIDI firmware update,** run `install` again. QIDI's update can replace its config files, and `status` says so when it has.

## Tools

All three only read; none changes a file.

- **Speed test.** `python3 ~/plus4-grease/tools/speed_test.py` moves the toolhead over the probing area at rising speeds, staying out of QIDI's no-print zones, and re-homes after each to find where steps start getting lost. Results go to `~/plus4-grease-speed-test-<date>.txt`. Results from more printers help decide whether 300 mm/s can go higher; please share yours in an issue.
- **Klipper report.** `python3 ~/plus4-grease/tools/klipper_report.py --all` reads `klippy.log` and the USB event log. It shows each board's chip and the motors it drives; how busy the boards, their serial links and the mainboard's Linux processor were during the last print; each Klipper start and what led to it; and for every shutdown ("Timer too close", "Lost communication", ...) what the numbers just before it point to: the Linux side stalling, a bad serial link, a board stepping too fast, a temperature reading out of range, or a board dropping off USB. Serial numbers are hidden.
- **Config comparison.** `python3 ~/plus4-grease/tools/config_diff.py` compares your `printer.cfg`, `gcode_macro.cfg`, Box files and `moonraker.conf` with QIDI's stock V2.1.1 copies in `stock/plus4-2.1.1/` (with `--firmware 1.6.0`, QIDI's 1.6.0 files), section by section: what you added, removed and changed, macro bodies as a line diff, and the SAVE_CONFIG block. Plus4 Grease's own edits are taken out first. Serial numbers are hidden. The result is also saved to `~/plus4-grease-config-diff-<date>.txt`. On a stock 1.8.2 printer it found no stock differences at all, only the owner's own changes.

What's known about the Plus 4's software and boards is in [docs/plus4-notes.md](docs/plus4-notes.md). `tools/collect_plus4.py` gathers the same information from a printer, read-only, with serial numbers removed.

## Help test on a stock Plus 4

Everything here has run on one Plus 4 so far, with a Beacon probe conversion; [docs/testing.md](docs/testing.md) says what was tested where. If you have a stock Plus 4 on QIDI's V2.1.1, 1.8.1 or 1.8.2, these help most, in this order, and none of them changes anything:

```
bash ~/plus4-grease/install.sh install --dry-run
python3 ~/plus4-grease/tools/config_diff.py
python3 ~/plus4-grease/tools/klipper_report.py
```

Then, if you're happy to, `install`, a print, and `klipper_report.py` again. Open an issue with the output. On a 1.6.0 printer, follow [docs/testing-1.6.0.md](docs/testing-1.6.0.md) instead. The tools leave out serial numbers and passwords, but read what you paste first.

### On firmware 1.8.1 and 1.8.2

QIDI sent 1.8.1 and 1.8.2 only as online updates and never published their files. QIDI did publish the 1.7.1 configs that came before them, and every Plus4 Grease edit finds the same stock text there as in V2.1.1. A stock Plus 4 on 1.8.2 has since been checked: its `printer.cfg`, `gcode_macro.cfg`, Box files and filament list have V2.1.1's stock text, and the dry run lists every change `available` ([docs/testing.md](docs/testing.md)). The standard changes have since been installed on that printer, and a print finished with no errors. What's expected, from [docs/plus4-notes.md](docs/plus4-notes.md#firmware-18x):

- **The config changes and `--box-dry`** should work as on V2.1.1. Box drying only reads things 1.7.1 already had (the Box heater, its humidity sensor, the slot sensors and the saved variables), and no filament's Box heat limit changed between them. The cool-down lock also needs QIDI's `E_LOAD`, `E_BOX` and `EXTRUDER_LOAD`, which install checks for, and QIDI's Box templates in `/home/mks`, which haven't been seen on 1.8.x yet; where they differ, install skips the lock and says so, and the print-start check still applies.
- **The new Fluidd's Box card** should show the slots and run Load, Unload, Eject, Read RFID and Plus4 Grease's drying. 1.8.x runs an earlier build of QIDI's Box software than V2.1.1, so the card may not show drying started from the touchscreen.
- **Moonraker:** QIDI's 1.7 and V2.1.1 Moonraker report the same API version, so the new Fluidd should connect. Untested.

The installer prints a line saying the firmware is untested. A dry run (`install --dry-run`, `fluidd install --dry-run`) shows what applies before anything changes.

### On firmware 1.6.0

QIDI's 1.6.0 (November 2024) came before the QIDI Box: its Klipper has no Box software, and its print start, pause and resume are older forms without the Box steps. Its print start also doesn't run Z tilt; QIDI added that in 1.7.0. So 1.6.0 has its own change list, [`grease/edits_v160.py`](grease/edits_v160.py), written and tested against QIDI's published 1.6.0 files alone (`stock/plus4-1.6.0/`), and changes made for 1.8.1 and later don't reach it.

- **Offered:** the bed mesh save wait, both probe speeds, the USB event log, `--board-fan` and `--balanced-chamber`, and the new Fluidd. The Z tilt speed only counts when Z tilt is run, since 1.6.0's print start doesn't run it.
- **Not offered:** the Box runout-flag wait (the loop isn't there) and everything under `--box-dry`.
- Install records the firmware; `status` and `uninstall` use the list it recorded. To compare a 1.6.0 printer's config with QIDI's: `python3 ~/plus4-grease/tools/config_diff.py --firmware 1.6.0`.

None of it has run on a 1.6.0 printer yet. If you have one, [docs/testing-1.6.0.md](docs/testing-1.6.0.md) lists what to run, in order.

## What's next

Candidates, each needing a test on a Plus 4 before it ships:


- On hold: saving the config in the background, as Valve Oil does. On a Beacon Plus 4, `tools/klipper_report.py` found no pause in Klipper's main loop during print start's config save (a Stats line every second throughout), so there's nothing to win there yet. A stock Plus 4's numbers would settle it for QIDI's `G29`.
- Fixes for QIDI Box bugs on the Plus 4, such as its Box software looking for the filament list in the wrong folder (`/home/qidi`).

## For developers

Tests run on a computer: `python3 -m unittest discover -s tests -v`. Everything under `grease/` and `tools/` runs on the printer's Python 3.7, so it has to stay within Python 3.7.

## Credits and license

Plus4 Grease is licensed under the GNU GPL v3; see [LICENSE](LICENSE). It builds on ideas from [Valve Oil](https://github.com/thelegendtubaguy/valve-oil) by TheLegendTubaGuy, also GPL v3, which does this for the QIDI Max 4, Plus 5, and Smart 5. [NOTICE.md](NOTICE.md) lists what comes from where. QIDI's config text it edits is QIDI's, published under the GPL v3 in [QIDITECH/QIDI_PLUS4](https://github.com/QIDITECH/QIDI_PLUS4).
