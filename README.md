# Plus4 Grease

Small, reversible improvements and diagnostic tools for the **QIDI Plus 4** on QIDI firmware **V2.1.1**, stock or converted to a Beacon probe.

> [!IMPORTANT]
> Plus4 Grease is an unofficial, independent project. It is not made or supported by QIDI, and it is **not Valve Oil**. Valve Oil's author doesn't support the Plus 4, so please don't take Plus4 Grease problems to the Valve Oil Discord or issue tracker. Open an issue here instead.

> [!CAUTION]
> Watch the first print after installing, and be ready to stop the printer. You use this at your own risk.

## What Plus4 Grease is

Plus4 Grease is an add-on for QIDI's own software on the Plus 4. It keeps QIDI's firmware, Klipper, Moonraker, Fluidd, touchscreen and Box software as they are, and makes a few small edits to QIDI's Klipper config where QIDI's settings cost time for nothing. Each edit is checked against QIDI's original text before it's made, the file is backed up first, and `uninstall` undoes it.

It also brings read-only tools for finding out what a Plus 4 is doing: a speed test, a Klipper report that explains shutdowns like "Timer too close" and "Lost communication", and a comparison of your config with QIDI's stock one.

The ideas come from [Valve Oil](https://github.com/thelegendtubaguy/valve-oil), which does this for QIDI's Max 4, Plus 5 and Smart 5. Plus4 Grease is a separate project, written for the Plus 4's older software: Klipper on Python 3.7, Debian 10, and the `mks` user. This is version 0.3.

## Plus4 Grease vs stock QIDI

| | Stock QIDI V2.1.1 | With Plus4 Grease |
|---|---|---|
| Clearing the Box runout flags at print start | 16 flags with a 0.1 s wait after each: 1.6 s | no waits; each save already finishes before the next command runs |
| Saving a new bed mesh (`G29`) | a fixed 5 s wait first | 0.5 s, as Valve Oil does on the Max 4 and Plus 5 |
| Z tilt: travel between probe points | 150 mm/s | 300 mm/s; each 255 mm trip takes about 0.9 s instead of 1.7 s |
| Bed mesh: travel between probe points | 150 mm/s | 300 mm/s; a full 9×9 mesh spends about 8 s less moving |
| USB devices connecting and disconnecting | only in Linux's log, which the Plus 4 keeps in RAM and loses when switched off | also in `~/printer_data/logs/plus4-grease-usb.log` on the eMMC, without serial numbers |
| When Klipper stops ("Timer too close", "Lost communication") | QIDI's generic message | `tools/klipper_report.py` says what the numbers just before it point to and matches USB events, so a Box rebooted by a power flicker shows as one |
| Firmware, Klipper, Moonraker, Fluidd, touchscreen, Box software | QIDI's | unchanged |

Probing itself is unchanged; only the travel between points is faster. The Plus 4's X/Y motors are open-loop, and Valve Oil's Plus 5 lost position at 565 mm/s, so the speed was measured first: on a tested Plus 4, `tools/speed_test.py` ran X/Y up to 500 mm/s at the full 20000 mm/s² over the probing area with no lost steps. 300 leaves room for printers that haven't been tested, and faster would save under 2 s more per full mesh.

## Stock and Beacon Plus 4s

There is one Plus4 Grease for both. Each change looks for QIDI's exact stock text and works from what it finds, so on a printer converted to a Beacon probe it applies what still fits and leaves the conversion's own changes alone.

| Change | Stock Plus 4 | Beacon conversion |
|---|---|---|
| Print start without the runout-flag waits | applies | applies where the conversion left `PRINT_START`'s flag loop as QIDI wrote it |
| Bed mesh save after 0.5 s | applies | skipped: the conversion's `G29` is its own |
| Z tilt and bed mesh at 300 mm/s | applies | a conversion usually sets its own speeds, so these are skipped unless you run `install --replace-own-speeds`, which sets them to 300 too and keeps a note of yours for `uninstall`. With a Beacon, the bed mesh speed is also its scan speed. |
| USB event log and the tools | applies | applies |

`install --dry-run` shows which changes apply on your printer before anything is touched. So far Plus4 Grease has been tested on a Beacon-converted Plus 4 with one Box; see [docs/testing.md](docs/testing.md). Results from a stock Plus 4 are wanted, especially for the bed mesh save change and the 300 mm/s probe travel with QIDI's own probe. `tools/config_diff.py` lists everything a printer's config changes from QIDI's stock one, which is a quick way to see what a conversion touched.

## How it stays safe

- **It only edits QIDI's stock text.** Each change looks for QIDI's exact lines from V2.1.1 and applies only where it finds them, once. If you've changed that part yourself, for example with a Beacon probe conversion, that change is skipped and your file is left as it is. The one exception is the probe speeds, and only when you ask with `--replace-own-speeds`. After the restart, install checks that Klipper really loaded the new speeds, since another included file can set them again.
- **Backups first.** Every file it changes is copied to `~/.plus4-grease/backups/` first.
- **Klipper has to start.** After a change it restarts Klipper. If Klipper doesn't come back ready, it puts your files back by itself.
- **Clean uninstall.** `uninstall` puts QIDI's lines back.
- **One system file pair, nothing else.** The USB event log is the only part outside Klipper's config: a udev rule in `/etc/udev/rules.d/99-plus4-grease-usb.rules` and its script in `/usr/local/lib/plus4-grease/`, written with `sudo` and owned by root, since udev runs the script as root. `uninstall` removes both and leaves the log.
- **It checks the printer.** It runs only on a Plus 4 (`/dev_info.txt` reads `QIDI@x-plus_4`) on firmware V2.1.1, as the `mks` user, and never while a print is running or paused.

## Install

You need SSH access to the printer as `mks`. QIDI's default password is `makerbase`.

**1. Get Plus4 Grease onto the printer.** Either:

- On the printer, if it can reach the internet:
  ```
  git clone https://github.com/JarvisAKF/Plus4-Grease ~/plus4-grease
  ```
- Or from your computer, with this repository downloaded (in PowerShell on Windows):
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
```

**After a QIDI firmware update,** run `install` again. QIDI's update can replace its config files, and `status` says so when it has.

## Tools

All three only read; none changes a file.

- **Speed test.** `python3 ~/plus4-grease/tools/speed_test.py` moves the toolhead over the probing area at rising speeds, staying out of QIDI's no-print zones, and re-homes after each to find where steps start getting lost. Results go to `~/plus4-grease-speed-test-<date>.txt`. Results from more printers help decide whether 300 mm/s can go higher; please share yours in an issue.
- **Klipper report.** `python3 ~/plus4-grease/tools/klipper_report.py --all` reads `klippy.log` and the USB event log. It shows each board's chip and the motors it drives; how busy the boards, their serial links and the mainboard's Linux processor were during the last print; each Klipper start and what led to it; and for every shutdown ("Timer too close", "Lost communication", ...) what the numbers just before it point to: the Linux side stalling, a bad serial link, a board stepping too fast, a temperature reading out of range, or a board dropping off USB. Serial numbers are hidden.
- **Config comparison.** `python3 ~/plus4-grease/tools/config_diff.py` compares your `printer.cfg`, `gcode_macro.cfg`, Box files and `moonraker.conf` with QIDI's stock V2.1.1 copies in `stock/plus4-2.1.1/`, section by section: what you added, removed and changed, macro bodies as a line diff, and the SAVE_CONFIG block. Plus4 Grease's own edits are taken out first. Serial numbers are hidden. The result is also saved to `~/plus4-grease-config-diff-<date>.txt`.

What's known about the Plus 4's software and boards is in [docs/plus4-notes.md](docs/plus4-notes.md). `tools/collect_plus4.py` gathers the same information from a printer, read-only, with serial numbers removed.

## What's next

Candidates, each needing a test on a Plus 4 before it ships:

- On hold: saving the config in the background, as Valve Oil does. On a Beacon Plus 4, `tools/klipper_report.py` found no pause in Klipper's main loop during print start's config save (a Stats line every second throughout), so there's nothing to win there yet. A stock Plus 4's numbers would settle it for QIDI's `G29`.
- Fixes for QIDI Box bugs on the Plus 4, such as its Box software looking for the filament list in the wrong folder (`/home/qidi`).

## For developers

Tests run on a computer: `python3 -m unittest discover -s tests -v`. Everything under `grease/` and `tools/` runs on the printer's Python 3.7, so it has to stay within Python 3.7.

## Credits and license

Plus4 Grease is licensed under the GNU GPL v3; see [LICENSE](LICENSE). It builds on ideas from [Valve Oil](https://github.com/thelegendtubaguy/valve-oil) by TheLegendTubaGuy, also GPL v3, which does this for the QIDI Max 4, Plus 5, and Smart 5. [NOTICE.md](NOTICE.md) lists what comes from where. QIDI's config text it edits is QIDI's, published under the GPL v3 in [QIDITECH/QIDI_PLUS4](https://github.com/QIDITECH/QIDI_PLUS4).
