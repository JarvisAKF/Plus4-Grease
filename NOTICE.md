# Notice

Plus4 Grease is free software under the GNU General Public License, version 3 (see `LICENSE`).

## Sources

- **Valve Oil** by TheLegendTubaGuy, https://github.com/thelegendtubaguy/valve-oil, GPL v3. Plus4 Grease follows its approach: guarded edits of QIDI's stock config, backups, and trimming fixed waits before changing speeds. The bed mesh change repeats the cut Valve Oil makes to QIDI's 5 s wait on the Max 4 and Plus 5. Based on Valve Oil's `dev` branch at commit `6670ec74a7253a483f30c08f4ada4d465925aa96`. Valve Oil's author doesn't support the Plus 4 or this project.
- **Fluidd** by the Fluidd team, https://github.com/fluidd-core/fluidd, GPL v3. `fluidd install` serves an upstream Fluidd release (v1.38.1), built by `tools/build_fluidd.sh` with `fluidd/plus4-grease.patch` applied.
- **Chakra Petch** by Cadson Demak, SIL Open Font License 1.1, through `@fontsource/chakra-petch` 5.3.0. The Overdrive persona of Plus4 Grease's Fluidd uses its Latin 500, 600 and 700 weights, bundled in the Fluidd zip.
- **Voice clips** in `fluidd/sounds/` were made for Plus4 Grease with Kokoro TTS (`kokoro-onnx`, Apache License 2.0, model `kokoro-v1.0`) and processed with ffmpeg. The lines are Plus4 Grease's own.
- **Valve Oil's Fluidd** by TheLegendTubaGuy, https://github.com/thelegendtubaguy/fluidd, GPL v3. The QIDI Box card in `fluidd/plus4-grease.patch` is ported from it, from commit `bb36dde`: the Box drawing (`QidiBoxFlow`, `QidiBoxUnit`, `QidiBoxSpool`, `QidiBoxNozzle`, `QidiBoxLoadedSummary`), the Box store, the filament dialog, the slot and task parsing in `src/util/qidi-box*.ts` with their tests, the Box icon and the English text. The card itself is Valve Oil's `QidiBoxCard` with every printer command taken out.
- **QIDI**, https://github.com/QIDITECH/QIDI_PLUS4, AGPL v3. `stock/plus4-2.1.1/` holds QIDI's stock config files from the Plus 4 V2.1.1 update package (`gcode_macro.cfg` SHA-256 `30d6aa8ad119fe4ce99005213e5bfbd9e7fa2889f17027c19ecfa260409082f0`), including its Box templates `cfg_with_0` to `cfg_with_4` from `/home/mks`, `stock/plus4-1.7.1/` QIDI's `printer.cfg`, `gcode_macro.cfg` and `officiall_filas_list.cfg` from the repository's `config/` folder at commit `ec595fc` (V1.7.1), and `stock/plus4-1.6.0/` its `printer.cfg` and `gcode_macro.cfg` from the same folder at commit `f2b5caf` (V1.6.0). They're used to test the edits and by `tools/config_diff.py`. The text the edits match is QIDI's.
- `tools/collect_plus4.py` and `docs/plus4-notes.md` were first written for a Plus 4 proposal to Valve Oil, and are carried over here.
