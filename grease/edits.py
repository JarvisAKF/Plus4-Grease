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
import os

Edit = collections.namedtuple("Edit", "file find replace")
# setting: the one option a feature sets, for printers where someone set it by hand (install
# --replace-own-speeds). None for features that only make their exact text edits.
# files: ((name, text), ...) a feature creates in the config folder and uninstall removes.
# option: the install switch (--board-fan) that turns on a change left off by default.
Feature = collections.namedtuple("Feature", "id title detail source edits setting files option",
                                 defaults=(None, None, None))
Setting = collections.namedtuple("Setting", "file section option value")

PROBE_MOVE_SPEED = 300
BOX_DRY_FILE = "plus4-grease-box-dry.cfg"
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), BOX_DRY_FILE), "r", encoding="utf-8",
          newline="") as _handle:
    BOX_DRY_CFG = _handle.read()
BOARD_FAN_FILE = "plus4-grease-board-fan.cfg"
BOARD_FAN_CFG = r'''# Plus4 Grease: temperature-driven mainboard fan for the QIDI Plus 4 (install --board-fan).
# From JarvisAKF's Plus 4, where it has run for over a year. It replaces QIDI's [controller_fan board_fan],
# which runs the fan at full speed whenever X/Y are enabled or the chamber heater is on.
# `bash ~/plus4-grease/install.sh uninstall` puts QIDI's fan back and removes this file.

[fan_generic board_fan]
pin: U_1:PC4
max_power: 1.0
shutdown_speed: 1.0        # full blast on Klipper shutdown, same as stock
cycle_time: 0.01
kick_start_time: 0.5
off_below: 0.15

# Mainboard STM32 temp. Stock [temperature_sensor GD32] reads 'mcu' (ttyS2),
# which is the toolhead board (extruder/ADXL/part fan live there), not the mainboard.
[temperature_sensor mainboard_mcu]
sensor_type: temperature_mcu
sensor_mcu: U_1

[delayed_gcode _BOARD_FAN_LOOP]
initial_duration: 5
gcode:
  # --- tuning knobs ---
  {% set drv_lo = 60.0 %}      # X/Y TMC2240 die temp where fan starts ramping
  {% set drv_hi = 70.0 %}      # X/Y TMC2240 die temp for 100%
  {% set mcu_lo = 45.0 %}      # mainboard MCU temp where fan starts ramping
  {% set mcu_hi = 65.0 %}      # mainboard MCU temp for 100%
  {% set floor  = 0.30 %}      # minimum speed while X/Y enabled or chamber heating
  # --- inputs (TMC2240 temp is null while the driver is disabled -> 0) ---
  {% set tx = printer["tmc2240 stepper_x"].temperature or 0 %}
  {% set ty = printer["tmc2240 stepper_y"].temperature or 0 %}
  {% set tm = printer["temperature_sensor mainboard_mcu"].temperature %}
  # --- proportional ramp, take the hottest demand ---
  {% set s_drv = ([tx, ty]|max - drv_lo) / (drv_hi - drv_lo) %}
  {% set s_mcu = (tm - mcu_lo) / (mcu_hi - mcu_lo) %}
  {% set spd = [s_drv, s_mcu, 0.0]|max %}
  {% set en = printer.stepper_enable.steppers %}
  {% set busy = en.stepper_x or en.stepper_y or printer["heater_generic chamber"].target > 0 %}
  {% if busy %}{% set spd = [spd, floor]|max %}{% endif %}
  SET_FAN_SPEED FAN=board_fan SPEED={"%.2f" % ([spd, 1.0]|min)}
  UPDATE_DELAYED_GCODE ID=_BOARD_FAN_LOOP DURATION=5
'''

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
        setting=Setting("printer.cfg", "z_tilt", "speed", PROBE_MOVE_SPEED),
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
        setting=Setting("printer.cfg", "bed_mesh", "speed", PROBE_MOVE_SPEED),
    ),
    Feature(
        id="board_fan",
        title="Board fan: driven by the X/Y driver and mainboard chip temperatures (install --board-fan)",
        detail=(
            "QIDI's [controller_fan board_fan] runs the mainboard fan at full speed whenever X/Y are enabled or "
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
        title="Chamber: heater follows an average of the toolhead chip and chamber thermistor (install --balanced-chamber)",
        detail=(
            "QIDI's chamber heater follows its chamber thermistor alone. This makes it follow the mean of the "
            "toolhead board's chip temperature (GD32, counted 3 times) and that thermistor (now "
            "[temperature_sensor chamber_probe], counted once), raises max_power from 0.4 to 0.6 and max_temp "
            "from 70 to 80 C as an overshoot buffer, and drops QIDI's 45-65 C target range and its raising of "
            "the bed to chamber + 25 C. Klipper shuts down if the mean passes 80 C or the sensors disagree by "
            "more than 70 C. QIDI's Chamber_Thermal_Protection_Sensor is left as it is and still shuts the "
            "printer down at 140 C."
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
    Feature(
        id="box_dry",
        title="Box drying with a timer and humidity control (install --box-dry)",
        detail=(
            "Adds PLUS4_BOX_DRY BOX=1 TEMP=45 HOURS=4 HUMIDITY=20 and PLUS4_BOX_DRY_STOP BOX=1, which the new "
            "Fluidd's Box card uses. Drying is the Box heater at a temperature, as QIDI's touchscreen does it "
            "(SET_HEATER_TEMPERATURE HEATER=heater_boxN), with a timer kept by Klipper and, if HUMIDITY is "
            "given, the heater switched off at or below that humidity and back on 5 points above it. It never "
            "goes above QIDI's Box limit for the filaments loaded (0 for PLA and TPU refuses to heat), refuses "
            "a loaded filament QIDI's list doesn't name, and stops if the Box heater is changed elsewhere."
        ),
        source="Plus4 Grease, from the command QIDI's touchscreen sends to dry the Box on V2.1.1.",
        edits=(
            Edit(
                file="printer.cfg",
                find=(
                    "[include KAMP_Settings.cfg]\n"
                    "[include box.cfg]\n"
                ),
                replace=(
                    "[include KAMP_Settings.cfg]\n"
                    "# Plus4 Grease (--box-dry): Box drying macros.\n"
                    "[include {}]\n"
                    "[include box.cfg]\n"
                ).format(BOX_DRY_FILE),
            ),
        ),
        files=((BOX_DRY_FILE, BOX_DRY_CFG),),
        option="box-dry",
    ),
)
