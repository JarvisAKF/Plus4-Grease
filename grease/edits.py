"""The changes Plus4 Grease makes, as exact text edits to QIDI's config files.

Each edit names one block of QIDI's stock text and what replaces it. An edit applies only when its stock
block is in the file exactly once, so a file someone changed by hand (a Beacon conversion, a community
mod) is left alone instead of overwritten. Uninstall puts the stock block back only where the replacement
is still there exactly once.

PROBE_MOVE_SPEED is the Plus 4's speed for the X/Y moves between probe points. tools/speed_test.py ran a
Plus 4's X/Y at up to 500 mm/s at its full 20000 mm/s^2 over the probing area with no lost steps (see
docs/testing.md). 300 leaves room for printers that haven't been tested; above it a full 9x9 mesh saves
under 2 s more.
"""
import collections

Edit = collections.namedtuple("Edit", "file find replace")
Feature = collections.namedtuple("Feature", "id title detail source edits")

PROBE_MOVE_SPEED = 300

FEATURES = (
    Feature(
        id="print_start_runout_dwell",
        title="Print start: no 1.6 s wait while clearing the Box runout flags",
        detail=(
            "QIDI's PRINT_START clears 16 runout flags with a 0.1 s G4 dwell after each one. Each "
            "SAVE_VARIABLE already finishes its file write before the next command runs, so the dwells "
            "only add 1.6 s of dead time to every print with a Box."
        ),
        source="Plus4 Grease; trims fixed dead time the way Valve Oil does on the Max 4 and Plus 5.",
        edits=(
            Edit(
                file="gcode_macro.cfg",
                find=(
                    "        {% for i in range(16) %}\n"
                    "            SAVE_VARIABLE VARIABLE=runout_{i} VALUE=0\n"
                    "            G4 P100\n"
                    "        {% endfor %}\n"
                ),
                replace=(
                    "        {% for i in range(16) %}\n"
                    "            SAVE_VARIABLE VARIABLE=runout_{i} VALUE=0\n"
                    "        {% endfor %}\n"
                ),
            ),
        ),
    ),
    Feature(
        id="bed_mesh_save_dwell",
        title="Bed mesh: 0.5 s instead of 5 s before saving a new mesh",
        detail=(
            "QIDI's G29 waits a fixed 5 s after measuring a mesh before SAVE_CONFIG_QD writes it to "
            "printer.cfg. BED_MESH_CALIBRATE has already finished by then. Valve Oil cut the same wait to "
            "0.5 s on the Max 4 and Plus 5; this does the same on the Plus 4, saving 4.5 s per print that "
            "measures a mesh."
        ),
        source="Valve Oil (Max 4 and Plus 5 bed mesh macros), github.com/thelegendtubaguy/valve-oil.",
        edits=(
            Edit(
                file="gcode_macro.cfg",
                find=(
                    "        BED_MESH_CALIBRATE PROFILE=kamp\n"
                    "        SAVE_VARIABLE VARIABLE=profile_name VALUE='\"kamp\"'\n"
                    "        G4 P5000\n"
                    "        SAVE_CONFIG_QD\n"
                ),
                replace=(
                    "        BED_MESH_CALIBRATE PROFILE=kamp\n"
                    "        SAVE_VARIABLE VARIABLE=profile_name VALUE='\"kamp\"'\n"
                    "        G4 P500\n"
                    "        SAVE_CONFIG_QD\n"
                ),
            ),
            Edit(
                file="gcode_macro.cfg",
                find=(
                    "            _BED_MESH_CALIBRATE PROFILE=default\n"
                    "            G4 P5000\n"
                    "            SAVE_CONFIG_QD\n"
                ),
                replace=(
                    "            _BED_MESH_CALIBRATE PROFILE=default\n"
                    "            G4 P500\n"
                    "            SAVE_CONFIG_QD\n"
                ),
            ),
        ),
    ),
    Feature(
        id="z_tilt_probe_moves",
        title="Z tilt: {} mm/s instead of 150 between probe points".format(PROBE_MOVE_SPEED),
        detail=(
            "Z_TILT_ADJUST travels the 255 mm between its two probe points at QIDI's 150 mm/s, up to three "
            "rounds per print. At {} each trip takes about 0.9 s instead of 1.7 s. Only the travel between "
            "points changes; the probing itself is the same.".format(PROBE_MOVE_SPEED)
        ),
        source=(
            "Valve Oil raises the same speed on the Plus 5 (to 400 mm/s, after 565 made its open-loop X/Y "
            "motors skip). The Plus 4 value comes from tools/speed_test.py."
        ),
        edits=(
            Edit(
                file="printer.cfg",
                find=(
                    "speed: 150\n"
                    "horizontal_move_z: 5\n"
                    "retries: 2\n"
                    "retry_tolerance: 0.05\n"
                ),
                replace=(
                    "speed: {}\n"
                    "horizontal_move_z: 5\n"
                    "retries: 2\n"
                    "retry_tolerance: 0.05\n"
                ).format(PROBE_MOVE_SPEED),
            ),
        ),
    ),
    Feature(
        id="bed_mesh_probe_moves",
        title="Bed mesh: {} mm/s instead of 150 between probe points".format(PROBE_MOVE_SPEED),
        detail=(
            "BED_MESH_CALIBRATE travels between probe points at QIDI's 150 mm/s. At {} a full 9x9 mesh spends "
            "about 8 s less moving, and smaller adaptive meshes save in proportion. With a Beacon this is "
            "also its scan speed. Only the travel between points changes; the probing itself is the "
            "same.".format(PROBE_MOVE_SPEED)
        ),
        source=(
            "Valve Oil raises the same speed on the Plus 5 (to 400 mm/s, after 565 made its open-loop X/Y "
            "motors skip). The Plus 4 value comes from tools/speed_test.py."
        ),
        edits=(
            Edit(
                file="printer.cfg",
                find=(
                    "[bed_mesh]\n"
                    "speed:150\n"
                    "horizontal_move_z:5\n"
                ),
                replace=(
                    "[bed_mesh]\n"
                    "speed:{}\n"
                    "horizontal_move_z:5\n"
                ).format(PROBE_MOVE_SPEED),
            ),
        ),
    ),
)
