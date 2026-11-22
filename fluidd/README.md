# Plus4 Grease's Fluidd changes

`tools/build_fluidd.sh` clones upstream Fluidd at a release tag, applies `plus4-grease.patch`, moves Fluidd's settings to their own Moonraker namespace, builds it, and packs the zip that `install.sh fluidd install` puts on the printer.

## plus4-grease.patch

A QIDI Box card on the dashboard (`box-card`, the ID QIDI's own Fluidd uses, so a layout copied from QIDI's page keeps its place). It shows each slot's filament, color and RFID state, the Box's humidity and temperature, which slot is loaded, the hub and toolhead sensors, tool mapping, auto-reload groups, a running Box step, and a failed step with QIDI's error. Its Load, Unload, Eject and Read RFID buttons send what QIDI's own Fluidd sends on V2.1.1 (`E_LOAD slot=N`, `E_UNLOAD slot=N`, `E_BOX slot=N`, `RFID_READ SLOT=slotN`). It's hidden when no Box is connected.

It's ported from Valve Oil's Fluidd (https://github.com/thelegendtubaguy/fluidd, commit `bb36dde`, GPL v3), written for QIDI's newer printers. The Plus 4's Box publishes the same objects on QIDI firmware V2.1.1 (`box_extras`, `multi_color_controller`, `box_stepper slotN`, `aht20_f heater_boxN`, `save_variables`), so the parsing is used as it is:

- copied unchanged: `src/util/qidi-box.ts`, `qidi-box-flow.ts` and their tests, and `qidi-box-task.ts` but for the one addition below; `src/store/qidiBox/`; `src/components/widgets/qidiBox/` `QidiBoxFlow`, `QidiBoxUnit`, `QidiBoxSpool`, `QidiBoxNozzle`, `QidiBoxLoadedSummary`; the `qidi_box` English text and the Box icon
- `src/util/qidi-box-task.ts`: one addition, `qidiBoxToolheadFilament`, which reads the Plus 4's `hall_filament_width_sensor` (filament while `Diameter` is above `min_diameter`) where QIDI's newer printers have a filament switch; the Box store and the loaded-slot check use it. Tested in `qidi-box-toolhead.spec.ts`.
- `QidiBoxCard.vue`: Valve Oil's card cut down to Load, Unload, Eject and Read RFID with QIDI's V2.1.1 commands; no dialogs, tool mapping, flow retry, jog or cut
- `QidiBoxSettingsDialog.vue`: Valve Oil's dialog cut down to QIDI's three Box settings, sent as QIDI's V2.1.1 page sends them
- `src/mixins/qidiBox.ts`: reads `officiall_filas_list.cfg` (Valve Oil's also reads the newer firmware's filament database)
- `src/util/qidi-box.ts`: one addition: a slot's nozzle and Box limits fall back to the `officiall_filas_list.cfg` entry with the slot's filament name. Tested in `qidi-box-plus4-limits.spec.ts`.
- the Box heater limit, from Valve Oil's Fluidd: `src/store/printer/getters.ts` and `types.ts` give heaters `targetMinTemp`/`targetMaxTemp` (a Box heater's capped by `qidiBox/getHeaterLimit`), and `TemperatureTargets.vue` enforces them
- small edits to register it: `src/store/index.ts`, `src/store/types.ts`, `src/store/layout/state.ts`, `src/views/Dashboard.vue`, `src/globals.ts`, a wait for Box commands, and two new lines of English text

To change it: clone Fluidd at the tag, `git apply` the patch, make the change, then `git add -A -N src && git diff -- src > plus4-grease.patch`. Bump `BUILD` in `grease/fluidd.py` and the build script, rebuild, and put the new SHA-256 in `grease/fluidd.py`.
