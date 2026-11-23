"""The changes Plus4 Grease makes on QIDI firmware 1.6.0, kept apart from the main list (edits.py).

1.6.0 (November 2024) is the Plus 4 before the QIDI Box: its Klipper has no Box modules, its printer.cfg
has no [include box.cfg], and its PRINT_START, PAUSE, RESUME, CANCEL_PRINT and PRINT_END are older forms
without the Box steps. Its PRINT_START doesn't run Z_TILT_ADJUST either; QIDI added that in 1.7.0. What
1.8.1 and later changed is in edits.py, and nothing here follows it: each edit below was written against
QIDI's own 1.6.0 files (stock/plus4-1.6.0, from QIDITECH/QIDI_PLUS4 at f2b5caf, tag Plus4_V1.6.0) and is
tested against them alone (tests/test_v160.py).

Left out on 1.6.0: the Box print-start wait (that loop isn't in 1.6.0's PRINT_START) and Box drying, its
print-start check and its cool-down lock (no Box). The feature ids are the same as in edits.py, so status
and uninstall read the same way.

Borrowed from edits.py, since they aren't QIDI's text: the Edit, Feature and Setting shapes, the 300 mm/s
probe move speed, and the board fan's own config file.
"""
from .edits import BOARD_FAN_CFG, BOARD_FAN_FILE, PROBE_MOVE_SPEED, Edit, Feature, Setting

FIRMWARE = ("V1.6.0",)
LABEL = "1.6.0"

FEATURES = (
    Feature(
        id="bed_mesh_save_dwell",
        title="Bed mesh: 0.5 s instead of 5 s before saving a new mesh",
        detail=(
            "1.6.0's G29 waits a fixed 5 s after measuring a mesh before SAVE_CONFIG_QD writes it to "
            "printer.cfg. BED_MESH_CALIBRATE has already finished by then. Valve Oil cut the same wait to "
            "0.5 s on the Max 4 and Plus 5; this does the same here, saving 4.5 s per print that measures a "
            "mesh."
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
            "Z_TILT_ADJUST travels the 255 mm between its two probe points at QIDI's 150 mm/s. At {} each "
            "trip takes about 0.9 s instead of 1.7 s. 1.6.0's PRINT_START doesn't run Z tilt, so this only "
            "counts when Z_TILT_ADJUST is run some other way, by hand for one. Only the travel between "
            "points changes; the probing itself is the same.".format(PROBE_MOVE_SPEED)
        ),
        source="The Plus 4 value comes from tools/speed_test.py; Valve Oil raises the same speed on the Plus 5.",
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
        setting=Setting("printer.cfg", "z_tilt", "speed", PROBE_MOVE_SPEED),
    ),
    Feature(
        id="bed_mesh_probe_moves",
        title="Bed mesh: {} mm/s instead of 150 between probe points".format(PROBE_MOVE_SPEED),
        detail=(
            "BED_MESH_CALIBRATE travels between probe points at QIDI's 150 mm/s. At {} a full 9x9 mesh spends "
            "about 8 s less moving, and smaller adaptive meshes save in proportion. 1.6.0's PRINT_START "
            "measures a mesh (G29) on every print. Only the travel between points changes; the probing itself "
            "is the same.".format(PROBE_MOVE_SPEED)
        ),
        source="The Plus 4 value comes from tools/speed_test.py; Valve Oil raises the same speed on the Plus 5.",
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
        setting=Setting("printer.cfg", "bed_mesh", "speed", PROBE_MOVE_SPEED),
    ),
    Feature(
        id="board_fan",
        title="Board fan: driven by the X/Y driver and mainboard chip temperatures (install --board-fan)",
        detail=(
            "1.6.0's [controller_fan board_fan] runs the mainboard fan at full speed whenever X/Y are enabled or "
            "the chamber heater is on. This replaces it with a fan that follows the hottest of the X/Y TMC2240 "
            "drivers (ramping from 60 to 70 C) and the mainboard chip (45 to 65 C), with a 30% floor while X/Y "
            "or the chamber heater are on, and full speed if Klipper shuts down. Checked every 5 s."
        ),
        source="JarvisAKF's Plus 4 board_fan.cfg, run for over a year.",
        edits=(
            Edit(
                file="printer.cfg",
                find=(
                    "[controller_fan board_fan]\n"
                    "pin:U_1:PC4\n"
                    "max_power:1.0\n"
                    "shutdown_speed:1.0\n"
                    "cycle_time:0.01\n"
                    "fan_speed: 1.0\n"
                    "heater:chamber\n"
                    "stepper:stepper_x,stepper_y\n"
                ),
                replace=(
                    "# Plus4 Grease (--board-fan): QIDI's board fan (controller_fan board_fan) is replaced\n"
                    "# by a temperature-driven fan in {}.\n"
                    "[include {}]\n"
                ).format(BOARD_FAN_FILE, BOARD_FAN_FILE),
            ),
        ),
        files=((BOARD_FAN_FILE, BOARD_FAN_CFG),),
        option="board-fan",
    ),
    Feature(
        id="balanced_chamber",
        title=("Chamber: heater follows an average of the toolhead chip and chamber thermistor "
               "(install --balanced-chamber)"),
        detail=(
            "1.6.0's chamber heater follows its chamber thermistor alone. This makes it follow the mean of the "
            "toolhead board's chip temperature (GD32, counted 3 times) and that thermistor (now "
            "[temperature_sensor chamber_probe], counted once), raises max_power from 0.4 to 0.6 and max_temp "
            "from 70 to 80 C as an overshoot buffer, and drops QIDI's 45-65 C target range and its raising of "
            "the bed to chamber + 25 C. Klipper shuts down if the mean passes 80 C or the sensors disagree by "
            "more than 70 C. QIDI's Chamber_Thermal_Protection_Sensor is left as it is."
        ),
        source="JarvisAKF's Plus 4 chamber setup, run for over a year at 65 C chamber targets.",
        edits=(
            Edit(
                file="printer.cfg",
                find=(
                    "[heater_generic chamber]\n"
                    "heater_pin:U_1:PC8\n"
                    "max_power:0.4\n"
                    "sensor_type:NTC 100K MGB18-104F39050L32\n"
                    "sensor_pin:U_1:PA1\n"
                    "\n"
                    "control = pid\n"
                    "pid_Kp=63.418 \n"
                    "pid_Ki=1.342 \n"
                    "pid_Kd=749.125\n"
                    "\n"
                    "min_temp:-100\n"
                    "max_temp:70\n"
                    "target_min_temp:45\n"
                    "target_max_temp:65\n"
                    "heat_with_heater_bed:True\n"
                    "heat_with_heater_bed_tem_add:25\n"
                ),
                replace=(
                    "# Plus4 Grease (--balanced-chamber): the chamber heater follows the mean of the toolhead\n"
                    "# board's chip temperature (GD32, counted 3 times) and QIDI's chamber thermistor (now\n"
                    "# chamber_probe, counted once). QIDI's Chamber_Thermal_Protection_Sensor is unchanged.\n"
                    "[temperature_sensor chamber_probe]\n"
                    "sensor_type:NTC 100K MGB18-104F39050L32\n"
                    "sensor_pin:U_1:PA1\n"
                    "\n"
                    "[heater_generic chamber]\n"
                    "heater_pin:U_1:PC8\n"
                    "max_power:0.6\n"
                    "sensor_type: temperature_combined\n"
                    "sensor_list: temperature_sensor GD32, temperature_sensor chamber_probe, "
                    "temperature_sensor GD32, temperature_sensor GD32\n"
                    "combination_method: mean\n"
                    "maximum_deviation: 70\n"
                    "\n"
                    "control = pid\n"
                    "pid_Kp=63.418 \n"
                    "pid_Ki=1.342 \n"
                    "pid_Kd=749.125\n"
                    "\n"
                    "min_temp:-100\n"
                    "max_temp:80\n"
                ),
            ),
        ),
        option="balanced-chamber",
    ),
)
