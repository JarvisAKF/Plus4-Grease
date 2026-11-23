"""Runs the Box drying macros (grease/plus4-grease-box-dry.cfg) and the cool-down lock (plus4-grease-box-lock.cfg)
the way Klipper renders them, against a pretend Plus 4 with one to four Boxes, to check the filament limits, the
timer, the humidity control, PLA/TPU drying and the cool-down lock.

Klipper's macros are Jinja2 templates with '{%' and '{' as delimiters; each line a macro outputs runs as a
command, and a nested macro renders only when its line runs. This copies that. It needs jinja2, Klipper's
template engine, and is skipped without it.
"""
import ast
import configparser
import re
import shlex
import unittest

from grease.edits import (BOX_DRY_CFG, BOX_DRY_FILE, BOX_LOCK_CFG, BOX_SETTINGS_CFG, FEATURES, PLA_OFF,
                          PLA_ON)

try:
    import jinja2
except ImportError:  # pragma: no cover
    jinja2 = None

PLA_SILK, ASA, ABS, PA6_CF, PETG, TPU = 4, 18, 11, 25, 39, 50
PLA_DRYING = BOX_SETTINGS_CFG.replace(PLA_OFF, PLA_ON)


def settings(**values):
    """A settings file with PLA/TPU drying on and these variables changed."""
    lines = []
    for line in PLA_DRYING.splitlines(True):
        key = line.partition(":")[0].strip()[len("variable_"):]
        if key in values:
            line = "variable_{}: {!r}\n".format(key, values[key])
        lines.append(line)
    return "".join(lines)


class MacroError(Exception):
    pass


# Klipper's own split of a G-code line (klippy/gcode.py): the command is the first run of letters and
# underscores plus the number right after it, so a name with a digit in the middle is cut there.
ARGS_R = re.compile("([A-Z_]+|[A-Z*])")


def klipper_command(line):
    parts = ARGS_R.split(line.upper())
    if "".join(parts[:2]) == "N":
        del parts[:2]
    if len(parts) >= 3 and parts[1] != "N":
        return parts[1] + parts[2].strip()
    return ""


class Status(dict):
    """printer[...] in a template: objects by name, and `in` for ones that exist."""


class Printer(object):
    def __init__(self, filaments, humidity=40.0, box_count=1, settings=None, lock=False, temperature=28.0):
        """filaments: {slot: filament ID} for the slots with filament at their inlet. settings: the text of
        plus4-grease-box-dry-settings.cfg, which Klipper reads after the defaults. lock: also load the
        wrappers around QIDI's load commands."""
        if jinja2 is None:
            raise unittest.SkipTest("jinja2 not installed")
        self.env = jinja2.Environment("{%", "%}", "{", "}")
        self.macros, self.delayed, self.renamed = {}, {}, {}
        parser = configparser.RawConfigParser(strict=False)
        text = BOX_DRY_CFG + "\n" + (settings or "") + "\n" + (BOX_LOCK_CFG if lock else "")
        # Klipper drops everything from a '#' to the end of the line before parsing.
        parser.read_string("\n".join(line.split("#", 1)[0] for line in text.splitlines()))
        initial = {}
        for section in parser.sections():
            kind, _, name = section.partition(" ")
            options = dict(parser.items(section))
            if kind == "gcode_macro":
                variables = {k[len("variable_"):]: ast.literal_eval(v) for k, v in options.items()
                             if k.startswith("variable_")}
                self.macros[name.upper()] = (self.env.from_string(options.get("gcode", "")), variables)
                if "rename_existing" in options:
                    self.renamed[options["rename_existing"].upper()] = name.upper()
            elif kind == "delayed_gcode":
                self.delayed[name] = self.env.from_string(options["gcode"])
                initial[name] = float(options.get("initial_duration", 0))
        variables = {"box_count": box_count}
        variables.update({"filament_slot{}".format(slot): fid for slot, fid in filaments.items()})
        self.objects = Status({
            "save_variables": {"variables": variables},
            "print_stats": {"state": "standby"},
            "hall_filament_width_sensor": {"Diameter": 0.0, "Raw": 0, "is_active": True},
            "configfile": {"settings": {"hall_filament_width_sensor": {"min_diameter": 0.3}}},
        })
        for box in range(1, box_count + 1):
            self.objects["aht20_f heater_box{}".format(box)] = {"humidity": humidity, "temperature": temperature}
            self.objects["heater_generic heater_box{}".format(box)] = {
                "target": 0.0, "temperature": temperature, "power": 0.0}
            for slot in range((box - 1) * 4, box * 4):
                self.objects["box_stepper slot{}".format(slot)] = {"runout_button": 0 if slot in filaments else 1}
        self.messages, self.qidi, self.dwells = [], [], 0
        self.scheduled = {name: duration for name, duration in initial.items() if duration > 0}
        # What a minute of G4 does to the Boxes: by default each Box with its heater off cools by 1 C.
        self.cooling = 1.0

    def view(self):
        status = Status(self.objects)
        for name, (_, variables) in self.macros.items():
            status["gcode_macro " + name] = dict(variables)
        return status

    def state(self, box=1):
        return self.macros["_GREASE_BOX_DRY_{}".format(box)][1]

    def target(self, box=1):
        return self.objects["heater_generic heater_box{}".format(box)]["target"]

    def heater(self, box=1):
        return self.objects["heater_generic heater_box{}".format(box)]

    def temp(self, value, box=1):
        self.heater(box)["temperature"] = value

    def printing(self, state="printing"):
        self.objects["print_stats"]["state"] = state

    def in_toolhead(self, slot, diameter=1.75):
        self.objects["save_variables"]["variables"]["last_load_slot"] = "slot{}".format(slot)
        self.objects["hall_filament_width_sensor"]["Diameter"] = diameter

    def settle(self):
        """Run the first minute after a Klipper start."""
        assert self.scheduled.get("_GREASE_BOX_DRY_TICK") == 15
        self.tick()

    def humidity(self, value, box=1):
        self.objects["aht20_f heater_box{}".format(box)]["humidity"] = value

    def raise_error(self, message):
        raise MacroError(message)

    def render(self, template, params, rawparams=""):
        return template.render(printer=self.view(), params=params, rawparams=rawparams,
                               action_raise_error=self.raise_error)

    def run(self, line):
        # Klipper ends a command's arguments at '#', ';' or '*' (a comment or a checksum).
        if re.search(r"[#;*]", line):
            raise AssertionError("Klipper would cut this line short: {!r}".format(line))
        words = shlex.split(line)
        command, params = klipper_command(line), {}
        if command != words[0].upper():
            raise AssertionError("Klipper reads {!r} as the command {!r}".format(line, command))
        for word in words[1:]:
            key, _, value = word.partition("=")
            params[key.upper()] = value
        rawparams = line[len(words[0]):].strip()
        if command == "SET_GCODE_VARIABLE":
            self.macros[params["MACRO"].upper()][1][params["VARIABLE"]] = ast.literal_eval(params["VALUE"])
        elif command == "SET_HEATER_TEMPERATURE":
            heater = self.objects["heater_generic " + params["HEATER"]]
            heater["target"] = float(params["TARGET"])
            heater["power"] = 0.5 if heater["target"] > 0 else 0.0
        elif command == "UPDATE_DELAYED_GCODE":
            self.scheduled[params["ID"]] = float(params["DURATION"])
        elif command == "RESPOND":
            self.messages.append(params["MSG"])
        elif command == "G4":
            # Klipper's delayed gcode can't run while a macro holds the G-code lock, so no tick here.
            self.dwells += 1
            for name, heater in self.objects.items():
                if name.startswith("heater_generic") and heater["target"] == 0:
                    heater["temperature"] = max(25.0, heater["temperature"] - self.cooling)
        elif command in self.renamed:
            self.qidi.append(command + (" " + rawparams if rawparams else ""))
        elif command in self.macros:
            self.script(self.render(self.macros[command][0], params, rawparams))
        else:
            raise AssertionError("unexpected command {}".format(line))

    def script(self, text):
        for line in text.splitlines():
            if line.strip():
                self.run(line.strip())

    def tick(self):
        """One minute: the delayed gcode runs if it was scheduled."""
        if self.scheduled.pop("_GREASE_BOX_DRY_TICK", 0) > 0:
            self.script(self.render(self.delayed["_GREASE_BOX_DRY_TICK"], {}))
            return True
        return False


class BoxDryTests(unittest.TestCase):
    def test_the_file_is_the_feature_file_and_parses(self):
        feature = next(f for f in FEATURES if f.id == "box_dry")
        self.assertEqual(feature.files, ((BOX_DRY_FILE, BOX_DRY_CFG),))
        self.assertEqual(feature.option, "box-dry")
        printer = Printer({1: ASA})
        self.assertIn("GREASE_BOX_DRY", printer.macros)
        self.assertIn("_GREASE_BOX_DRY_TICK", printer.delayed)

    def test_no_hash_outside_a_comment(self):
        # Klipper cuts every config line at its first '#', so one inside a macro (a Jinja {# #} comment, say)
        # would break the template.
        for text in (BOX_DRY_CFG, BOX_LOCK_CFG, BOX_SETTINGS_CFG):
            for line in text.splitlines():
                if not line.lstrip().startswith("#"):
                    self.assertNotIn("#", line)

    def test_klipper_reads_every_macro_name_whole(self):
        for name in Printer({}).macros:
            self.assertEqual(klipper_command(name + " BOX=1"), name)
        self.assertEqual(klipper_command("PLUS4_BOX_DRY BOX=1"), "PLUS4")  # why 0.9.0's names never ran

    @staticmethod
    def stock_limits(version):
        import os
        import re
        here = os.path.dirname(os.path.abspath(__file__))
        listed, current = {}, None
        with open(os.path.join(here, "..", "stock", "plus4-" + version, "officiall_filas_list.cfg")) as handle:
            for line in handle:
                header = re.match(r"\[fila(\d+)\]", line)
                if header:
                    current = int(header.group(1))
                elif current is not None and "=" in line:
                    key, value = (part.strip() for part in line.split("=", 1))
                    listed.setdefault(current, {})[key] = value
        return {fid: int(entry["box_max_temp"]) for fid, entry in listed.items()
                if entry.get("filament") and entry.get("box_max_temp", "").isdigit()}

    def test_limits_match_qidis_v2_1_1_filament_list(self):
        self.assertEqual(Printer({}).macros["_GREASE_BOX_DRY_LIMITS"][1]["limits"], self.stock_limits("2.1.1"))

    def test_limits_agree_with_qidis_1_7_1_filament_list(self):
        # 1.7.1 lists fewer filaments; every one it lists has the same Box limit as in V2.1.1.
        limits = Printer({}).macros["_GREASE_BOX_DRY_LIMITS"][1]["limits"]
        older = self.stock_limits("1.7.1")
        self.assertTrue(older)
        for fid, limit in older.items():
            self.assertEqual(limits.get(fid), limit, "fila{}".format(fid))

    def test_pla_loaded_refuses_to_heat(self):
        printer = Printer({0: PLA_SILK, 1: ASA})
        with self.assertRaises(MacroError) as caught:
            printer.run("GREASE_BOX_DRY BOX=1")
        self.assertIn("slot 1A has PLA or TPU", str(caught.exception))
        self.assertIn("variable_pla_drying: True", str(caught.exception))
        self.assertEqual(printer.target(), 0)
        self.assertEqual(printer.state()["active"], 0)

    def test_filament_saved_for_an_empty_slot_does_not_count(self):
        printer = Printer({1: ASA})
        printer.objects["save_variables"]["variables"]["filament_slot0"] = PLA_SILK
        printer.run("GREASE_BOX_DRY BOX=1")
        self.assertEqual(printer.target(), 45)

    def test_defaults_to_the_lowest_limit_of_the_loaded_filaments(self):
        printer = Printer({0: ABS, 2: PA6_CF})
        printer.run("GREASE_BOX_DRY BOX=1")
        self.assertEqual(printer.target(), 45)
        self.assertEqual(printer.state()["active"], 1)
        self.assertEqual(printer.state()["minutes_left"], 240)
        self.assertEqual(printer.scheduled["_GREASE_BOX_DRY_TICK"], 60)
        self.assertIn("Box 1: drying at 45 C for 4 h", printer.messages[-1])

    def test_temperature_above_the_limit_is_refused(self):
        printer = Printer({1: ASA})
        with self.assertRaises(MacroError) as caught:
            printer.run("GREASE_BOX_DRY BOX=1 TEMP=50")
        self.assertIn("1 to 45 C", str(caught.exception))
        self.assertEqual(printer.target(), 0)

    def test_unknown_filament_is_refused(self):
        for fid in (0, 99):
            printer = Printer({1: fid})
            with self.assertRaises(MacroError) as caught:
                printer.run("GREASE_BOX_DRY BOX=1")
            self.assertIn("slot 1B", str(caught.exception))

    def test_a_box_that_is_not_there_is_refused(self):
        with self.assertRaises(MacroError):
            Printer({1: ASA}).run("GREASE_BOX_DRY BOX=2")

    def test_timer_runs_out_and_turns_the_heater_off(self):
        printer = Printer({1: ASA})
        printer.run("GREASE_BOX_DRY BOX=1 TEMP=40 HOURS=0.05")
        self.assertEqual(printer.state()["minutes_left"], 3)
        self.assertTrue(printer.tick())
        self.assertTrue(printer.tick())
        self.assertEqual(printer.target(), 40)
        self.assertTrue(printer.tick())
        self.assertEqual(printer.target(), 0)
        self.assertEqual(printer.state()["active"], 0)
        self.assertEqual(printer.messages[-1], "Box 1: drying finished.")
        printer.tick()  # the minute keeps running for the cool-down count; drying stays off
        self.assertEqual(printer.target(), 0)
        self.assertEqual(printer.state()["active"], 0)

    def test_hours_zero_runs_until_stopped(self):
        printer = Printer({1: ASA})
        printer.run("GREASE_BOX_DRY BOX=1 HOURS=0")
        for _ in range(300):
            self.assertTrue(printer.tick())
        self.assertEqual(printer.target(), 45)
        printer.run("GREASE_BOX_DRY_STOP BOX=1")
        self.assertEqual(printer.target(), 0)
        self.assertEqual(printer.state()["active"], 0)
        printer.tick()  # the minute keeps running for the cool-down count; drying stays off
        self.assertEqual(printer.target(), 0)
        self.assertEqual(printer.state()["active"], 0)

    def test_humidity_switches_the_heater_off_and_on(self):
        printer = Printer({1: ASA}, humidity=40)
        printer.run("GREASE_BOX_DRY BOX=1 HOURS=0 HUMIDITY=20")
        self.assertEqual(printer.target(), 45)
        printer.humidity(20)
        printer.tick()
        self.assertEqual(printer.target(), 0)
        self.assertEqual(printer.state()["heating"], 0)
        self.assertEqual(printer.state()["active"], 1)
        printer.humidity(24)
        printer.tick()
        self.assertEqual(printer.target(), 0)
        printer.humidity(25)
        printer.tick()
        self.assertEqual(printer.target(), 45)
        self.assertEqual(printer.state()["heating"], 1)

    def test_already_dry_starts_with_the_heater_off(self):
        printer = Printer({1: ASA}, humidity=15)
        printer.run("GREASE_BOX_DRY BOX=1 HUMIDITY=20")
        self.assertEqual(printer.target(), 0)
        self.assertEqual(printer.state()["active"], 1)
        self.assertTrue(printer.tick())

    def test_heater_changed_elsewhere_ends_drying_and_leaves_it_alone(self):
        printer = Printer({1: ASA})
        printer.run("GREASE_BOX_DRY BOX=1")
        printer.objects["heater_generic heater_box1"]["target"] = 30.0
        printer.tick()
        self.assertEqual(printer.state()["active"], 0)
        self.assertEqual(printer.target(), 30.0)
        self.assertIn("changed elsewhere", printer.messages[-1])
        printer.tick()
        self.assertEqual(printer.target(), 30.0)
        self.assertEqual(printer.state()["active"], 0)

    def test_each_of_four_boxes_dries_on_its_own(self):
        # Box 1 has PLA (locked); Boxes 2 to 4 have ASA, ABS + PA6-CF, and nothing.
        printer = Printer({0: PLA_SILK, 4: ASA, 8: ABS, 9: PA6_CF}, box_count=4)
        with self.assertRaises(MacroError):
            printer.run("GREASE_BOX_DRY BOX=1")
        printer.run("GREASE_BOX_DRY BOX=2 HOURS=1")
        printer.run("GREASE_BOX_DRY BOX=3 HOURS=0 HUMIDITY=20")
        printer.run("GREASE_BOX_DRY BOX=4 HOURS=0")
        self.assertEqual([printer.target(box) for box in (1, 2, 3, 4)], [0, 45, 45, 65])
        printer.humidity(15, box=3)
        printer.tick()
        self.assertEqual([printer.target(box) for box in (1, 2, 3, 4)], [0, 45, 0, 65])
        printer.run("GREASE_BOX_DRY_STOP BOX=4")
        self.assertEqual([printer.state(box)["active"] for box in (1, 2, 3, 4)], [0, 1, 1, 0])
        for _ in range(60):
            printer.tick()
        self.assertEqual(printer.state(2)["active"], 0)
        self.assertEqual(printer.state(3)["active"], 1)

    def test_bad_hours_and_humidity_are_refused(self):
        for line in ("GREASE_BOX_DRY BOX=1 HOURS=-1", "GREASE_BOX_DRY BOX=1 HOURS=49",
                     "GREASE_BOX_DRY BOX=1 HUMIDITY=95"):
            with self.assertRaises(MacroError):
                Printer({1: ASA}).run(line)



class PlaDryingTests(unittest.TestCase):
    def test_settings_file_gives_the_defaults(self):
        plain, stock = Printer({}), Printer({}, settings=BOX_SETTINGS_CFG)
        self.assertEqual(plain.macros["_GREASE_BOX_DRY_SETTINGS"][1], stock.macros["_GREASE_BOX_DRY_SETTINGS"][1])
        self.assertIs(Printer({}, settings=PLA_DRYING).macros["_GREASE_BOX_DRY_SETTINGS"][1]["pla_drying"], True)

    def test_settings_are_kept_in_range(self):
        printer = Printer({}, settings=settings(pla_max_temp=90, unlock_temp=5, cool_minutes=500,
                                                print_start="later"))
        printer.run("GREASE_BOX_DRY_SETTINGS")
        self.assertEqual(printer.messages[-1], "PLA/TPU drying: on, up to 50 C. A Box holding PLA or TPU unlocks "
                         "at or below 30 C and 120 min after its heater last ran. Print start with such a Box "
                         "still locked: wait.")

    def test_pla_dries_up_to_pla_max_temp(self):
        printer = Printer({0: PLA_SILK, 1: ASA}, settings=PLA_DRYING)
        printer.run("GREASE_BOX_DRY BOX=1 HOURS=2")
        self.assertEqual(printer.target(), 45)
        self.assertEqual(printer.state()["pla"], 1)
        self.assertEqual(printer.state()["cool_left"], 30)
        self.assertIn("stays locked for loading", printer.messages[-1])
        printer = Printer({0: TPU}, settings=settings(pla_max_temp=50))
        printer.run("GREASE_BOX_DRY BOX=1")
        self.assertEqual(printer.target(), 50)
        with self.assertRaises(MacroError) as caught:
            Printer({0: PLA_SILK}, settings=PLA_DRYING).run("GREASE_BOX_DRY BOX=1 TEMP=50")
        self.assertIn("1 to 45 C", str(caught.exception))

    def test_a_higher_limit_filament_beside_pla_is_held_to_pla_max_temp(self):
        printer = Printer({0: PLA_SILK, 1: PA6_CF}, settings=PLA_DRYING)
        printer.run("GREASE_BOX_DRY BOX=1")
        self.assertEqual(printer.target(), 45)

    def test_limit_report_follows_the_setting(self):
        off, on = Printer({0: PLA_SILK}), Printer({0: PLA_SILK}, settings=PLA_DRYING)
        off.run("_GREASE_BOX_DRY_LIMIT BOX=1")
        on.run("_GREASE_BOX_DRY_LIMIT BOX=1")
        self.assertEqual(off.messages[-1], "Box 1 heater limit: 0 C (PLA or TPU in 1A)")
        self.assertEqual(on.messages[-1], "Box 1 heater limit: 45 C (PLA or TPU in 1A)")

    def test_no_pla_drying_during_a_print(self):
        for state in ("printing", "paused"):
            printer = Printer({0: PLA_SILK}, settings=PLA_DRYING)
            printer.printing(state)
            with self.assertRaises(MacroError) as caught:
                printer.run("GREASE_BOX_DRY BOX=1")
            self.assertIn("only dried while nothing is printing", str(caught.exception))
            self.assertEqual(printer.target(), 0)

    def test_asa_still_dries_during_a_print(self):
        printer = Printer({1: ASA}, settings=PLA_DRYING)
        printer.printing()
        printer.run("GREASE_BOX_DRY BOX=1")
        self.assertEqual(printer.target(), 45)

    def test_no_pla_drying_with_that_boxs_filament_in_the_toolhead(self):
        printer = Printer({0: PLA_SILK, 2: ASA}, settings=PLA_DRYING)
        printer.in_toolhead(2)
        with self.assertRaises(MacroError) as caught:
            printer.run("GREASE_BOX_DRY BOX=1")
        self.assertIn("slot 1C's filament is in the toolhead", str(caught.exception))
        printer.in_toolhead(2, diameter=0.0)  # QIDI keeps last_load_slot after an unload; the sensor is clear
        printer.run("GREASE_BOX_DRY BOX=1")
        self.assertEqual(printer.target(), 45)

    def test_qidis_loaded_slot_counts_too(self):
        # V2.1.1's box_extras keeps its own loaded_slot; JarvisAKF's printer showed slot16 (the external spool)
        # with last_load_slot slot-1 and the toolhead sensor reading 0.76 mm.
        printer = Printer({0: PLA_SILK, 1: ASA}, settings=PLA_DRYING)
        printer.objects["save_variables"]["variables"]["last_load_slot"] = "slot-1"
        printer.objects["hall_filament_width_sensor"]["Diameter"] = 0.763
        printer.objects["box_extras"] = {"loaded_slot": "slot16"}
        printer.run("GREASE_BOX_DRY BOX=1")
        self.assertEqual(printer.target(), 45)
        printer.run("GREASE_BOX_DRY_STOP BOX=1")
        printer.objects["box_extras"]["loaded_slot"] = "slot1"
        with self.assertRaises(MacroError) as caught:
            printer.run("GREASE_BOX_DRY BOX=1")
        self.assertIn("slot 1B's filament is in the toolhead", str(caught.exception))

    def test_another_boxs_filament_in_the_toolhead_is_fine(self):
        printer = Printer({0: PLA_SILK, 4: ASA}, settings=PLA_DRYING, box_count=2)
        printer.in_toolhead(4)
        printer.run("GREASE_BOX_DRY BOX=1")
        self.assertEqual(printer.target(1), 45)

    def test_without_the_sensor_the_toolhead_counts_as_loaded(self):
        printer = Printer({0: PLA_SILK}, settings=PLA_DRYING)
        printer.in_toolhead(0, diameter=0.0)
        del printer.objects["hall_filament_width_sensor"]
        with self.assertRaises(MacroError):
            printer.run("GREASE_BOX_DRY BOX=1")


class LockTests(unittest.TestCase):
    def dried(self, settings=PLA_DRYING):
        """A Box with PLA in 1A and ASA in 1B that just finished a 3-minute PLA drying run at 45 C."""
        printer = Printer({0: PLA_SILK, 1: ASA}, settings=settings, lock=True)
        printer.settle()
        printer.run("GREASE_BOX_DRY BOX=1 HOURS=0.05")
        printer.temp(45)
        for _ in range(3):
            printer.tick()
        self.assertEqual(printer.target(), 0)
        printer.heater()["power"] = 0.0
        return printer

    def test_loading_pla_from_a_cooling_box_is_refused(self):
        printer = self.dried()
        for line in ("E_LOAD SLOT=0", "E_LOAD SLOT=slot0", "E_BOX SLOT=0", "EXTRUDER_LOAD SLOT=slot0"):
            with self.assertRaises(MacroError) as caught:
                printer.run(line)
            self.assertIn("Box 1 is cooling after heating (45 C now, it unlocks at or below 35 C and in about 30 min)",
                          str(caught.exception))
        self.assertEqual(printer.qidi, [])

    def test_other_loads_go_straight_to_qidis_command(self):
        printer = self.dried()
        for line in ("E_LOAD SLOT=1", "E_LOAD SLOT=16", "E_LOAD", "E_BOX SLOT=slot1", "EXTRUDER_LOAD SLOT=slot1"):
            printer.run(line)
        self.assertEqual(printer.qidi, ["_GREASE_QIDI_E_LOAD SLOT=1", "_GREASE_QIDI_E_LOAD SLOT=16",
                                        "_GREASE_QIDI_E_LOAD", "_GREASE_QIDI_E_BOX SLOT=slot1",
                                        "_GREASE_QIDI_EXTRUDER_LOAD SLOT=slot1"])

    def test_unknown_filament_is_not_locked(self):
        printer = Printer({0: 99}, settings=PLA_DRYING, lock=True)
        printer.run("GREASE_BOX_DRY_STOP BOX=1")
        printer.macros["_GREASE_BOX_DRY_1"][1].update(cool_left=30, hot=1)
        printer.run("E_LOAD SLOT=0")
        self.assertEqual(printer.qidi, ["_GREASE_QIDI_E_LOAD SLOT=0"])

    def test_unlocks_after_cool_minutes_and_at_unlock_temp(self):
        printer = self.dried()
        for minute in range(29):
            printer.temp(44 - minute * 0.5)
            printer.tick()
        with self.assertRaises(MacroError):
            printer.run("E_LOAD SLOT=0")  # 1 min to go
        printer.tick()
        self.assertEqual(printer.state()["cool_left"], 0)
        printer.temp(36)
        with self.assertRaises(MacroError) as caught:
            printer.run("E_LOAD SLOT=0")  # time's up, but still warm
        self.assertIn("36 C now, it unlocks at or below 35 C)", str(caught.exception))
        printer.temp(35)
        printer.run("E_LOAD SLOT=0")
        self.assertEqual(printer.qidi, ["_GREASE_QIDI_E_LOAD SLOT=0"])
        printer.tick()
        self.assertEqual(printer.state()["hot"], 0)
        printer.temp(37)  # the room warms up later: not locked, nothing heated it
        printer.run("E_LOAD SLOT=0")
        self.assertEqual(len(printer.qidi), 2)

    def test_any_heating_locks_pla_even_with_pla_drying_off(self):
        # QIDI's touchscreen dries ASA; then a PLA spool goes in while the Box is warm.
        printer = Printer({1: ASA}, lock=True)
        printer.settle()
        printer.heater().update(target=45.0, power=0.6, temperature=45.0)
        printer.tick()
        printer.heater().update(target=0.0, power=0.0)
        printer.tick()
        printer.objects["save_variables"]["variables"]["filament_slot0"] = PLA_SILK
        printer.objects["box_stepper slot0"]["runout_button"] = 0
        with self.assertRaises(MacroError):
            printer.run("E_LOAD SLOT=0")
        self.assertEqual(printer.state()["cool_left"], 29)

    def test_klipper_restart_in_a_warm_room_doesnt_lock(self):
        printer = Printer({0: PLA_SILK}, lock=True, temperature=38.0)
        printer.settle()
        printer.run("E_LOAD SLOT=0")
        self.assertEqual(printer.qidi, ["_GREASE_QIDI_E_LOAD SLOT=0"])

    def test_klipper_restart_with_a_box_still_hot_locks(self):
        printer = Printer({0: PLA_SILK}, lock=True, temperature=44.0)
        printer.settle()
        self.assertEqual((printer.state()["cool_left"], printer.state()["hot"]), (30, 1))
        with self.assertRaises(MacroError):
            printer.run("E_LOAD SLOT=0")

    def test_a_tool_change_during_a_print_waits(self):
        printer = self.dried()
        printer.macros["_GREASE_BOX_DRY_1"][1]["cool_left"] = 3
        printer.temp(37)
        printer.printing()
        printer.run("EXTRUDER_LOAD SLOT=slot0")
        self.assertEqual(printer.dwells, 3)  # the 3 minutes left; the Box is under 35 C by then
        self.assertEqual(printer.qidi, ["_GREASE_QIDI_EXTRUDER_LOAD SLOT=slot0"])
        self.assertTrue(any(m.endswith(" Waiting.") for m in printer.messages))
        self.assertEqual(printer.messages[-1], "Box 1 has cooled to 34 C. Going on.")
        self.assertEqual((printer.state()["cool_left"], printer.state()["hot"]), (0, 0))

    def test_wait_keeps_going_while_hot_and_reports_every_5_minutes(self):
        printer = self.dried()
        printer.macros["_GREASE_BOX_DRY_1"][1]["cool_left"] = 0
        printer.temp(47)
        printer.printing()
        printer.run("EXTRUDER_LOAD SLOT=slot0")
        self.assertEqual(printer.dwells, 12)
        self.assertIn("Box 1: 37 C, 10 min into the cool-down wait.", printer.messages)

    def test_wait_gives_up_after_two_hours(self):
        printer = self.dried()
        printer.cooling = 0.0  # a room at 45 C
        printer.printing()
        with self.assertRaises(MacroError) as caught:
            printer.run("EXTRUDER_LOAD SLOT=slot0")
        self.assertEqual(printer.dwells, 120)
        self.assertIn("still at 45 C after 2 hours", str(caught.exception))
        self.assertIn("raise unlock_temp", str(caught.exception))
        self.assertEqual(printer.qidi, [])


class PrintStartTests(unittest.TestCase):
    def test_nothing_to_wait_for(self):
        printer = Printer({0: PLA_SILK, 1: ASA}, settings=PLA_DRYING)
        printer.settle()
        printer.run("_GREASE_BOX_PRINT_CHECK")
        self.assertEqual((printer.dwells, printer.messages), (0, []))

    def test_waits_for_a_cooling_box_with_pla(self):
        printer = LockTests.dried(LockTests())
        printer.printing()
        printer.run("_GREASE_BOX_PRINT_CHECK")
        self.assertEqual(printer.dwells, 30)
        self.assertTrue(any(m.endswith("The print waits for it before heating anything.") for m in printer.messages))
        self.assertEqual(printer.messages[-1], "Box 1 has cooled to 25 C. Going on.")

    def test_a_box_without_pla_is_not_waited_for(self):
        printer = Printer({1: ASA}, settings=PLA_DRYING)
        printer.settle()
        printer.run("GREASE_BOX_DRY BOX=1")
        printer.tick()
        printer.run("_GREASE_BOX_PRINT_CHECK")
        self.assertEqual(printer.dwells, 0)
        self.assertEqual(printer.target(), 45)

    def test_cancel_mode_stops_the_print(self):
        printer = LockTests.dried(LockTests(), settings=settings(print_start="cancel"))
        with self.assertRaises(MacroError) as caught:
            printer.run("_GREASE_BOX_PRINT_CHECK")
        self.assertIn("The print wasn't started", str(caught.exception))
        self.assertEqual(printer.dwells, 0)

    def test_pla_drying_is_stopped_for_a_print(self):
        printer = Printer({0: PLA_SILK}, settings=PLA_DRYING)
        printer.settle()
        printer.run("GREASE_BOX_DRY BOX=1 HOURS=4")
        printer.temp(45)
        printer.tick()
        printer.printing()
        printer.run("_GREASE_BOX_PRINT_CHECK")
        self.assertEqual(printer.state()["active"], 0)
        self.assertEqual(printer.target(), 0)
        self.assertIn("Box 1: drying stopped for the print. PLA and TPU aren't dried during a print.",
                      printer.messages)
        self.assertEqual(printer.dwells, 30)

    def test_each_box_is_checked(self):
        printer = Printer({0: PLA_SILK, 4: PLA_SILK, 8: ASA}, settings=PLA_DRYING, box_count=3)
        printer.settle()
        printer.macros["_GREASE_BOX_DRY_2"][1].update(cool_left=4, hot=1)
        printer.macros["_GREASE_BOX_DRY_3"][1].update(cool_left=9, hot=1)  # no PLA there
        printer.temp(30, box=2)
        printer.run("_GREASE_BOX_PRINT_CHECK")
        self.assertEqual(printer.dwells, 4)


if __name__ == "__main__":
    unittest.main()
