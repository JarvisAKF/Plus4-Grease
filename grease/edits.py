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

# older: replacement texts an earlier Plus4 Grease version wrote, or what QIDI's rewrite of a file left of
# them. Install turns one into the current replacement (the feature shows as 'update'), and uninstall puts
# QIDI's text back from it.
Edit = collections.namedtuple("Edit", "file find replace older", defaults=((),))
# setting: the one option a feature sets, for printers where someone set it by hand (install
# --replace-own-speeds). None for features that only make their exact text edits.
# files: ((name, text), ...) a feature creates in the config folder and uninstall removes.
# option: the install switch (--board-fan) that turns on a change left off by default.
# replaces: ((name, sha256), ...) of files an earlier Plus4 Grease version wrote for this change, which
# install updates and uninstall removes as its own.
# requires: the id of a feature this one only works with. It's skipped while that one can't be applied.
# user_files: (UserFile, ...) the feature writes once for the user to edit (settings). They don't count
# toward the feature's status, install never overwrites them, and uninstall removes one only while it's
# still one of its default texts.
# commands: QIDI commands the feature renames (rename_existing). Klipper won't start if one is missing, so
# install skips the feature when the running Klipper doesn't have them all.
# A file name starting with ~/ is in the mks home folder, not the config folder: QIDI's root-owned Box
# templates, which are written with sudo and keep their owner and mode.
Feature = collections.namedtuple("Feature",
                                 "id title detail source edits setting files option replaces requires user_files "
                                 "commands",
                                 defaults=(None, None, None, None, None, None, None))
Setting = collections.namedtuple("Setting", "file section option value")
# settle(text or None, options) -> (new text or None for no change, note or ""). describe(text) -> str.
UserFile = collections.namedtuple("UserFile", "name defaults settle describe")

PROBE_MOVE_SPEED = 300


def _ours(name):
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name), "r", encoding="utf-8",
              newline="") as handle:
        return handle.read()


BOX_DRY_FILE = "plus4-grease-box-dry.cfg"
BOX_DRY_CFG = _ours(BOX_DRY_FILE)
BOX_LOCK_FILE = "plus4-grease-box-lock.cfg"
BOX_LOCK_CFG = _ours(BOX_LOCK_FILE)
BOX_SETTINGS_FILE = "plus4-grease-box-dry-settings.cfg"
BOX_SETTINGS_CFG = _ours(BOX_SETTINGS_FILE)
PLA_OFF = "variable_pla_drying: False\n"
PLA_ON = "variable_pla_drying: True\n"
BOX_TEMPLATES = ("~/cfg_with_1", "~/cfg_with_2", "~/cfg_with_3", "~/cfg_with_4")
# The lock's include line in box.cfg and the templates. QIDI's box_detect rewrites box.cfg through Python's
# configparser (seen right after a Klipper restart): comments go, each section is followed by a blank line,
# and on the printer's Python 3.7 a section name ends at its first ']'. So the include is a plain section
# with a '?' pattern (nothing is included if the file is gone) and no comment, and the inserted text is what
# that rewrite writes back.
BOX_LOCK_INCLUDE = "[include plus4-grease-box-loc?.cfg]\n"
# 0.13.0 and 0.13.1 used a '[k]' pattern and a comment, which that rewrite cut to a line matching no file.
BOX_LOCK_OLDER = (
    "[include box1.cfg]\n"
    "# Plus4 Grease (--box-dry): Box cool-down lock. A pattern: nothing if the file is gone.\n"
    "[include plus4-grease-box-loc[k].cfg]\n",
    "[include box1.cfg]\n\n[include plus4-grease-box-loc[k]\n",
)


def _settle_box_settings(text, options):
    """The settings file: written once (PLA/TPU drying on with --box-dry-pla); afterwards --box-dry-pla
    only switches pla_drying on."""
    want_pla = "box-dry-pla" in options
    if text is None:
        return (BOX_SETTINGS_CFG.replace(PLA_OFF, PLA_ON) if want_pla else BOX_SETTINGS_CFG,
                "Wrote your Box drying settings to {} (PLA/TPU drying {}).".format(
                    BOX_SETTINGS_FILE, "on" if want_pla else "off"))
    if not want_pla:
        return None, ""
    lines = text.splitlines(True)
    if PLA_ON in lines:
        return None, ""
    if lines.count(PLA_OFF) == 1:
        return text.replace(PLA_OFF, PLA_ON), "Turned PLA/TPU drying on in {}.".format(BOX_SETTINGS_FILE)
    return None, ("{} has no line 'variable_pla_drying: False' to switch, so it's left as you have it. "
                  "Set variable_pla_drying: True there yourself.".format(BOX_SETTINGS_FILE))


def _describe_box_settings(text):
    value = "?"
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key.strip() == "variable_pla_drying":
            value = rest.split("#")[0].strip()
    on = value.lower() in ("true", "1", "yes", "on")
    return "PLA/TPU drying {} in {} (GREASE_BOX_DRY_SETTINGS shows all the settings)".format(
        "on" if on else "off", BOX_SETTINGS_FILE)


BOX_SETTINGS = UserFile(BOX_SETTINGS_FILE, (BOX_SETTINGS_CFG, BOX_SETTINGS_CFG.replace(PLA_OFF, PLA_ON)),
                        _settle_box_settings, _describe_box_settings)
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
        title="Box drying with a timer, humidity control and optional PLA/TPU drying (install --box-dry)",
        detail=(
            "Adds GREASE_BOX_DRY BOX=1 TEMP=45 HOURS=4 HUMIDITY=20 and GREASE_BOX_DRY_STOP BOX=1, which the new "
            "Fluidd's Box card uses. It sets the Box heater (SET_HEATER_TEMPERATURE HEATER=heater_boxN) with "
            "a timer kept by Klipper and, if HUMIDITY is given, switches the heater off at or below that "
            "humidity and back on 5 points above it; QIDI's own ENABLE_BOX_DRY, which the touchscreen uses, "
            "has a timer but no humidity control. It never "
            "goes above QIDI's Box limit for the filaments loaded, refuses "
            "a loaded filament QIDI's list doesn't name, and stops if the Box heater is changed elsewhere. "
            "QIDI's limit for PLA and TPU is 0; with pla_drying on in {} (install --box-dry-pla turns it on) "
            "they can be dried up to 45 C, never during a print or with that Box's filament in the toolhead, "
            "and the Box then stays locked for loading them until it has cooled."
        ).format(BOX_SETTINGS_FILE),
        source="Plus4 Grease's own, for the Plus 4's Box heater on V2.1.1.",
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
        replaces=(
            # 0.9.0's file, whose PLUS4_BOX_DRY macros Klipper couldn't call (it reads that name as PLUS4).
            (BOX_DRY_FILE, "2f30602eb7986401a4943e2c86c7dbf3a908330b35eb1ad64a12865870978f5e"),
            # 0.9.1 to 0.12.0's, without PLA/TPU drying or the cool-down lock.
            (BOX_DRY_FILE, "4062df48c530b28ed10d0eb1f9e536f8a19bc5cf06773b1febcfc8530a62dfe0"),
            # 0.13.0 to 0.13.2's, whose '[s]' include of the settings file Klipper on Python 3.7 read as a
            # pattern matching nothing, so the settings (PLA/TPU drying on) were never loaded.
            (BOX_DRY_FILE, "2b1fe61222c8a4e5480e379116deddfaec726f0b443229d31a0320fa79546bf4"),
        ),
        user_files=(BOX_SETTINGS,),
    ),
    Feature(
        id="box_dry_print_start",
        title="Box check at print start (install --box-dry)",
        detail=(
            "Adds _GREASE_BOX_PRINT_CHECK as the first line of PRINT_START, before anything heats. A print "
            "doesn't start while a Box holding PLA or TPU is drying or still cooling after heating, and says "
            "which Box and how long, so a print never has to wait for a Box partway through. A Box without "
            "PLA or TPU in it dries during a print as before. The line does nothing once Box drying is removed."
        ),
        source="Plus4 Grease's own, from JarvisAKF's account of PLA jamming in the Box's warm feed tubes.",
        edits=(
            Edit(
                file="gcode_macro.cfg",
                find=(
                    "[gcode_macro PRINT_START]\n"
                    "gcode:\n"
                    "    AUTOTUNE_SHAPERS\n"
                ),
                replace=(
                    "[gcode_macro PRINT_START]\n"
                    "gcode:\n"
                    "    # Plus4 Grease (--box-dry): no print while a Box holding PLA or TPU dries or cools.\n"
                    "    {% if 'gcode_macro _GREASE_BOX_PRINT_CHECK' in printer %}\n"
                    "    _GREASE_BOX_PRINT_CHECK\n"
                    "    {% endif %}\n"
                    "    AUTOTUNE_SHAPERS\n"
                ),
            ),
        ),
        option="box-dry",
        requires="box_dry",
    ),
    Feature(
        id="box_dry_lock",
        title="Box cool-down lock on loading PLA and TPU (install --box-dry)",
        detail=(
            "Puts {} in front of QIDI's E_LOAD, E_BOX and EXTRUDER_LOAD. Loading PLA or TPU from a Box still "
            "cooling after heating is refused, never waited for. It's included from box.cfg and from "
            "QIDI's Box templates (/home/mks/cfg_with_1 to cfg_with_4, which QIDI copies to box.cfg when the "
            "number of Boxes changes); the templates are root's, so this asks sudo. A printer with no Box "
            "connected skips it. QIDI rewrites box.cfg from the templates through Python's configparser, so the "
            "include is written in the form that survives that."
        ).format(BOX_LOCK_FILE),
        source="Plus4 Grease's own, from JarvisAKF's account of PLA jamming in the Box's warm feed tubes.",
        edits=tuple(
            Edit(
                file=name,
                find="[include box1.cfg]\n",
                replace="[include box1.cfg]\n\n" + BOX_LOCK_INCLUDE,
                older=BOX_LOCK_OLDER,
            )
            for name in ("box.cfg",) + BOX_TEMPLATES
        ),
        files=((BOX_LOCK_FILE, BOX_LOCK_CFG),),
        option="box-dry",
        requires="box_dry",
        commands=("E_LOAD", "E_BOX", "EXTRUDER_LOAD"),
    ),
)
