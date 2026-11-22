# Plus4 Grease's Fluidd changes

`tools/build_fluidd.sh` clones upstream Fluidd at a release tag, applies `plus4-grease.patch`, moves Fluidd's settings to their own Moonraker namespace, builds it, and packs the zip that `install.sh fluidd install` puts on the printer.

## plus4-grease.patch

A read-only QIDI Box card on the dashboard (`box-card`, the ID QIDI's own Fluidd uses, so a layout copied from QIDI's page keeps its place). It shows each slot's filament, color and RFID state, the Box's humidity and temperature, which slot is loaded, the hub and toolhead sensors, tool mapping, auto-reload groups, a running Box step, and a failed step with QIDI's error. It sends nothing to the printer. It's hidden when no Box is connected.

It's ported from Valve Oil's Fluidd (https://github.com/thelegendtubaguy/fluidd, commit `bb36dde`, GPL v3), written for QIDI's newer printers. The Plus 4's Box publishes the same objects on QIDI firmware V2.1.1 (`box_extras`, `multi_color_controller`, `box_stepper slotN`, `aht20_f heater_boxN`, `save_variables`), so the parsing is used as it is:

- copied unchanged: `src/util/qidi-box.ts`, `qidi-box-flow.ts`, `qidi-box-task.ts` and their tests; `src/store/qidiBox/`; `src/components/widgets/qidiBox/` `QidiBoxFlow`, `QidiBoxUnit`, `QidiBoxSpool`, `QidiBoxNozzle`, `QidiBoxLoadedSummary`; the `qidi_box` English text and the Box icon
- `QidiBoxCard.vue`: Valve Oil's card with the buttons, dialogs and commands taken out
- small edits to register it: `src/store/index.ts`, `src/store/types.ts`, `src/store/layout/state.ts`, `src/views/Dashboard.vue`, `src/globals.ts`, and two new lines of English text

To change it: clone Fluidd at the tag, `git apply` the patch, make the change, then `git add -A -N src && git diff -- src > plus4-grease.patch`. Bump `BUILD` in `grease/fluidd.py` and the build script, rebuild, and put the new SHA-256 in `grease/fluidd.py`.
