# Plus4 Grease: notes for Claude

Plus4 Grease is an add-on for QIDI's own software on the QIDI Plus 4: faster print start, Box drying with a timer and
humidity control (and optional PLA/TPU drying with a cool-down lock), a USB event log, diagnostics tools, and an
upstream Fluidd v1.38.1 with Plus 4 cards on port 81. It keeps QIDI's firmware, Klipper, Moonraker, touchscreen and Box
software as they are and only edits QIDI's config text, which `uninstall` puts back. Read `README.md` for what users
see and `docs/plus4-notes.md` for how QIDI's software behaves.

## Rules that always apply

- **No hardware identifiers in the repo.** MCU serial numbers, Box and Beacon USB serial numbers, `/dev/serial/by-id/`
  names and anything from `config/MCU_ID.cfg`, `box.cfg` or `saved_variables.cfg` that identifies a board are
  redacted before they go into a commit, a doc, a test fixture or an issue. Don't repeat them in replies either.
- **No private material.** QIDI's touchscreen project file (`.HMI`) and anything else QIDI sent privately stays out of
  the repo. No email addresses, testers' names, passwords or private service addresses in docs.
- **The printer runs Python 3.7.3** (Debian 10). Everything under `grease/` and `tools/` must run on it: no 3.8+
  syntax or library calls. Run `python3 tools/py37check.py grease/*.py tools/*.py` before committing.
- **Include paths use `?`, never `[x]`.** Python 3.7's configparser (QIDI's `box_detect.so` and Klipper's
  `configfile` both use it) ends a section name at the first `]`, so `[include foo[x].cfg]` breaks.
  `tests/test_py37_headers.py` checks every header Plus4 Grease writes.
- **`box.cfg` is rewritten by QIDI.** `box_detect.so` regenerates it from `/home/mks/cfg_with_1`..`cfg_with_4` at boot,
  dropping comments, writing `key : value` and tab-indenting multi-line values. Anything that must survive goes in
  those templates too, in a form that survives the rewrite (`tests/test_box_rewrite.py`).
- **Edits match QIDI's exact stock text.** `stock/` holds QIDI's files (1.6.0, 1.7.1, 2.1.1). Each `Edit` in
  `grease/edits.py` finds QIDI's lines and is skipped if they aren't there; earlier Plus4 Grease forms go in `older` so
  install updates them and uninstall reverts them. Firmware 1.6.0 has its own list in `grease/edits_v160.py`; the
  firmware recorded at install decides what `status` and `uninstall` use.
- **On the printer: read-only unless the owner asks.** Never restart Klipper, run `install`/`uninstall`, or send
  G-code that moves or heats during a print. Commands needing `sudo` need the owner's password; don't type or store
  passwords and don't set up password-free sudo. `fluidd install` only swaps web files and reloads nginx, so it's safe
  mid-print; `install` and `uninstall` restart Klipper.
- **Commits go to `main`** unless asked otherwise, one commit per change with a clear message. The GitHub release is
  made by the owner by hand, with the Fluidd zip attached.

## Layout

- `install.sh`: entry point on the printer (`install`, `uninstall`, `status`, `fluidd install|remove`, options like
  `--dry-run`, `--box-dry`, `--box-dry-pla`, `--board-fan`, `--balanced-chamber`).
- `grease/`: `core.py` (plan, apply, revert, state), `edits.py` / `edits_v160.py` (the changes), `fluidd.py` (the
  Fluidd install: `BUILD` and `BUNDLE_SHA256` must match the zip), `klipper.py`, `system.py` (udev USB log), and the
  `.cfg` files it installs.
- `tools/`: `klipper_report.py` (reads klippy.log and the USB log after a shutdown), `config_diff.py`,
  `collect_plus4.py`, `speed_test.py`, `build_fluidd.sh`, `py37check.py`.
- `fluidd/`: `plus4-grease.patch` (all Plus4 Grease changes to upstream Fluidd v1.38.1), `sounds/` (Overdrive voice
  clips), `README.md` (where each Fluidd change lives).
- `tests/`: unittest suite for everything above. `docs/testing.md`: the log of what was tested where.

## Commands

- Tests: `python3 -m unittest discover -s tests -v` (all must pass).
- 3.7 check: `python3 tools/py37check.py grease/*.py tools/*.py`.
- Fluidd: clone Fluidd v1.38.1, `git apply fluidd/plus4-grease.patch`, then work there. Before regenerating the patch,
  run its checks: `vitest run`, `vue-tsc --noEmit -p tsconfig.app.json`, `eslint` on the changed files. Regenerate with
  `git add -A -- . ':!pnpm-lock.yaml' ':!public/sounds'` and `git diff --cached HEAD -- . ':!pnpm-lock.yaml' ':!public/sounds' > fluidd/plus4-grease.patch`.
- Fluidd zip: `bash tools/build_fluidd.sh` (Node and pnpm). Bump its default build number, then put the printed sha256
  and the build number in `grease/fluidd.py`.
- On the printer: `bash ~/plus4-grease/install.sh install --dry-run` first, always; after a "Timer too close" or other
  shutdown, run `python3 ~/plus4-grease/tools/klipper_report.py` before restarting anything.

## A release

Bump `VERSION` in `grease/__init__.py`, add a `CHANGELOG.md` entry, update `README.md` for anything a user sees, add a
row to `docs/testing.md` saying exactly what was checked and where (a computer, or which printer and firmware), and
keep the tests passing. Docs are plain and short, and say what was verified on a printer and what wasn't.

## Open as of 2026-11-25

- **`--box-dry` and QIDI's touchscreen program:** on the owner's printer the Box stopped loading at print start
  ("Filament NOT present", then QDE_004_005 on resume) once QIDI's touchscreen program replaced qbdisplay, and loaded
  again with `--box-dry` off. A tester's touchscreen stopped registering newly loaded filament. The first suspect is the
  lock's wrappers around QIDI's `E_LOAD`, `E_BOX` and `EXTRUDER_LOAD` (`rename_existing`). The README says to hold off.
- **"Timer too close" on `mcu` during the Beacon mesh scan**, near X187 Y171, also with Plus4 Grease uninstalled. Z
  microsteps are already 32. Waiting for the next one to read the USB log with `klipper_report.py`.
- **Filament width sensor:** QIDI commented out Klipper's flow compensation. On TPU the reading follows the toolhead's Y
  position (the Box tube pulling the filament in the sensor), so an opt-in `--flow-comp` is on hold; if built, it needs
  averaging, a two-point drill-bit calibration, tight limits and flexibles left off. The width card (Fluidd build 15)
  hasn't been tried on a printer yet.
- qbdisplay flicker fix: pull request #2 to CharlyBrownFR/qbdisplay-plus4, fixed and waiting for his pre-release test.
