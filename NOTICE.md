# Notice

Plus4 Grease is free software under the GNU General Public License, version 3 (see `LICENSE`).

## Sources

- **Valve Oil** by TheLegendTubaGuy, https://github.com/thelegendtubaguy/valve-oil, GPL v3. Plus4 Grease follows its approach: guarded edits of QIDI's stock config, backups, and trimming fixed waits before changing speeds. The bed mesh change repeats the cut Valve Oil makes to QIDI's 5 s wait on the Max 4 and Plus 5. Based on Valve Oil's `dev` branch at commit `6670ec74a7253a483f30c08f4ada4d465925aa96`. Valve Oil's author doesn't support the Plus 4 or this project.
- **QIDI**, https://github.com/QIDITECH/QIDI_PLUS4, GPL v3. `tests/stock_gcode_macro_2.1.1.cfg` is QIDI's `gcode_macro.cfg` from the Plus 4 V2.1.1 update package (SHA-256 `30d6aa8ad119fe4ce99005213e5bfbd9e7fa2889f17027c19ecfa260409082f0`), used to test the edits. The text the edits match is QIDI's.
- `tools/collect_plus4.py` and `docs/plus4-notes.md` were first written for a Plus 4 proposal to Valve Oil, and are carried over here.
