# Plus4 Grease

Small, reversible improvements for the **QIDI Plus 4** on QIDI firmware **V2.1.1**.

> [!IMPORTANT]
> Plus4 Grease is an unofficial, independent project. It is not made or supported by QIDI, and it is **not Valve Oil**. Valve Oil's author doesn't support the Plus 4, so please don't take Plus4 Grease problems to the Valve Oil Discord or issue tracker. Open an issue here instead.

> [!CAUTION]
> Watch the first print after installing, and be ready to stop the printer. You use this at your own risk.

## What it changes

| Change | What you get |
|---|---|
| Print start: no 1.6 s wait while clearing the Box runout flags | QIDI's `PRINT_START` waits 0.1 s after clearing each of 16 flags. Each save already finishes before the next command, so the waits are dead time. |
| Bed mesh: 0.5 s instead of 5 s before saving a new mesh | QIDI's `G29` waits a fixed 5 s after measuring before it saves the mesh. Valve Oil made the same cut on the Max 4 and Plus 5. |
| Z tilt: 300 mm/s instead of 150 between probe points | Each 255 mm trip between `Z_TILT_ADJUST`'s two points takes about 0.9 s instead of 1.7 s. Only the travel changes, not the probing. |
| Bed mesh: 300 mm/s instead of 150 between probe points | A full 9×9 mesh spends about 8 s less moving; adaptive meshes save in proportion. With a Beacon it's also the scan speed. Only the travel changes, not the probing. |
| USB event log | A line in `~/printer_data/logs/plus4-grease-usb.log` each time a USB device (the Box, a Beacon, a board) connects or disconnects, kept on the eMMC. The Plus 4 keeps Linux's own logs in RAM, so switching the printer off loses them. `tools/klipper_report.py` uses it to tell "Lost communication" from a Box switched off or unplugged. No serial numbers are written. |

The two speed changes are in `printer.cfg` (`speed:` under `[z_tilt]` and `[bed_mesh]`). The Plus 4's X/Y motors are open-loop, and Valve Oil's Plus 5 lost position at 565 mm/s, so this was measured first: on a tested Plus 4, `tools/speed_test.py` ran X/Y up to 500 mm/s at the full 20000 mm/s² over the probing area with no lost steps. 300 leaves room for printers that haven't been tested; faster would save under 2 s more per full mesh.

A speed you've set yourself is left alone unless you ask: `install --replace-own-speeds` sets it to 300 too, keeps a note of yours, and `uninstall` puts yours back. After the restart, install checks that Klipper really loaded 300, since another included file can set the same speed again.

That's version 0.3: the installer, with checks and backups, two changes that trim waiting, two that speed up probing, and the USB event log. What's been tried on real printers is in [docs/testing.md](docs/testing.md). More follows as each change is tested on a Plus 4. See [What's next](#whats-next).

## How it stays safe

- **It only edits QIDI's stock text.** Each change looks for QIDI's exact lines from V2.1.1 and applies only where it finds them, once. If you've changed that part yourself, for example with a Beacon probe conversion, that change is skipped and your file is left as it is.
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

## What's next

Candidates, each needing a test on a Plus 4 before it ships:

- On hold: saving the config in the background, as Valve Oil does. On a Beacon Plus 4, `tools/klipper_report.py` found no pause in Klipper's main loop during print start's config save (a Stats line every second throughout), so there's nothing to win there yet. A stock Plus 4's numbers would settle it for QIDI's `G29`.
- Fixes for QIDI Box bugs on the Plus 4, such as its Box software looking for the filament list in the wrong folder (`/home/qidi`).

**Speed test.** `python3 ~/plus4-grease/tools/speed_test.py` moves the toolhead over the probing area at rising speeds, staying out of QIDI's no-print zones, and re-homes after each to find where steps start getting lost. It changes no files, and results go to `~/plus4-grease-speed-test-<date>.txt`. Results from more printers help decide whether 300 mm/s can go higher; please share yours in an issue.

**Klipper report.** `python3 ~/plus4-grease/tools/klipper_report.py --all` reads `klippy.log` and says how busy each board and the Pi were during the last print, which motors each board drives, and, for every time Klipper shut down ("Timer too close", "Lost communication", ...), what the numbers just before it point to: the Pi stalling, a bad serial link, a board stepping too fast, or a temperature reading out of range. It only reads the log.

What's known about the Plus 4's software is in [docs/plus4-notes.md](docs/plus4-notes.md). `tools/collect_plus4.py` gathers the same information from a printer, read-only, with serial numbers removed.

## For developers

Tests run on a computer: `python3 -m unittest discover -s tests -v`. Everything under `grease/` and `tools/` runs on the printer's Python 3.7, so it has to stay within Python 3.7.

## Credits and license

Plus4 Grease is licensed under the GNU GPL v3; see [LICENSE](LICENSE). It builds on ideas from [Valve Oil](https://github.com/thelegendtubaguy/valve-oil) by TheLegendTubaGuy, also GPL v3, which does this for the QIDI Max 4, Plus 5, and Smart 5. [NOTICE.md](NOTICE.md) lists what comes from where. QIDI's config text it edits is QIDI's, published under the GPL v3 in [QIDITECH/QIDI_PLUS4](https://github.com/QIDITECH/QIDI_PLUS4).
