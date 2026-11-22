"""Runs the Box drying macros (grease/plus4-grease-box-dry.cfg) the way Klipper renders them, against a pretend
Plus 4 with one Box, to check the filament limits, the timer and the humidity control.

Klipper's macros are Jinja2 templates with '{%' and '{' as delimiters; each line a macro outputs runs as a
command, and a nested macro renders only when its line runs. This copies that. It needs jinja2, Klipper's
template engine, and is skipped without it.
"""
import ast
import configparser
import re
import shlex
import unittest

from grease.edits import BOX_DRY_CFG, FEATURES, BOX_DRY_FILE

try:
    import jinja2
except ImportError:  # pragma: no cover
    jinja2 = None

PLA_SILK, ASA, ABS, PA6_CF, PETG = 4, 18, 11, 25, 39


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
    def __init__(self, filaments, humidity=40.0, box_count=1):
        """filaments: {slot: filament ID} for the slots with filament at their inlet."""
        if jinja2 is None:
            raise unittest.SkipTest("jinja2 not installed")
        self.env = jinja2.Environment("{%", "%}", "{", "}")
        self.macros, self.delayed = {}, {}
        parser = configparser.RawConfigParser(strict=False)
        # Klipper drops everything from a '#' to the end of the line before parsing.
        parser.read_string("\n".join(line.split("#", 1)[0] for line in BOX_DRY_CFG.splitlines()))
        for section in parser.sections():
            kind, _, name = section.partition(" ")
            options = dict(parser.items(section))
            if kind == "gcode_macro":
                variables = {k[len("variable_"):]: ast.literal_eval(v) for k, v in options.items()
                             if k.startswith("variable_")}
                self.macros[name.upper()] = (self.env.from_string(options.get("gcode", "")), variables)
            elif kind == "delayed_gcode":
                self.delayed[name] = self.env.from_string(options["gcode"])
        variables = {"box_count": box_count}
        variables.update({"filament_slot{}".format(slot): fid for slot, fid in filaments.items()})
        self.objects = Status({"save_variables": {"variables": variables}})
        for box in range(1, box_count + 1):
            self.objects["aht20_f heater_box{}".format(box)] = {"humidity": humidity, "temperature": 28.0}
            self.objects["heater_generic heater_box{}".format(box)] = {"target": 0.0, "temperature": 28.0}
            for slot in range((box - 1) * 4, box * 4):
                self.objects["box_stepper slot{}".format(slot)] = {"runout_button": 0 if slot in filaments else 1}
        self.messages, self.scheduled = [], {}

    def view(self):
        status = Status(self.objects)
        for name, (_, variables) in self.macros.items():
            status["gcode_macro " + name] = dict(variables)
        return status

    def state(self, box=1):
        return self.macros["_GREASE_BOX_DRY_{}".format(box)][1]

    def target(self, box=1):
        return self.objects["heater_generic heater_box{}".format(box)]["target"]

    def humidity(self, value, box=1):
        self.objects["aht20_f heater_box{}".format(box)]["humidity"] = value

    def raise_error(self, message):
        raise MacroError(message)

    def render(self, template, params):
        return template.render(printer=self.view(), params=params, action_raise_error=self.raise_error)

    def run(self, line):
        words = shlex.split(line)
        command, params = klipper_command(line), {}
        if command != words[0].upper():
            raise AssertionError("Klipper reads {!r} as the command {!r}".format(line, command))
        for word in words[1:]:
            key, _, value = word.partition("=")
            params[key.upper()] = value
        if command == "SET_GCODE_VARIABLE":
            self.macros[params["MACRO"].upper()][1][params["VARIABLE"]] = ast.literal_eval(params["VALUE"])
        elif command == "SET_HEATER_TEMPERATURE":
            self.objects["heater_generic " + params["HEATER"]]["target"] = float(params["TARGET"])
        elif command == "UPDATE_DELAYED_GCODE":
            self.scheduled[params["ID"]] = float(params["DURATION"])
        elif command == "RESPOND":
            self.messages.append(params["MSG"])
        elif command in self.macros:
            self.script(self.render(self.macros[command][0], params))
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

    def test_klipper_reads_every_macro_name_whole(self):
        for name in Printer({}).macros:
            self.assertEqual(klipper_command(name + " BOX=1"), name)
        self.assertEqual(klipper_command("PLUS4_BOX_DRY BOX=1"), "PLUS4")  # why 0.9.0's names never ran

    def test_limits_match_qidis_v2_1_1_filament_list(self):
        import os
        import re
        here = os.path.dirname(os.path.abspath(__file__))
        listed, current = {}, None
        with open(os.path.join(here, "..", "stock", "plus4-2.1.1", "officiall_filas_list.cfg")) as handle:
            for line in handle:
                header = re.match(r"\[fila(\d+)\]", line)
                if header:
                    current = int(header.group(1))
                elif current is not None and "=" in line:
                    key, value = (part.strip() for part in line.split("=", 1))
                    listed.setdefault(current, {})[key] = value
        expected = {fid: int(entry["box_max_temp"]) for fid, entry in listed.items()
                    if entry.get("filament") and entry.get("box_max_temp", "").isdigit()}
        self.assertEqual(Printer({}).macros["_GREASE_BOX_DRY_LIMITS"][1]["limits"], expected)

    def test_pla_loaded_refuses_to_heat(self):
        printer = Printer({0: PLA_SILK, 1: ASA})
        with self.assertRaises(MacroError) as caught:
            printer.run("GREASE_BOX_DRY BOX=1")
        self.assertIn("can't be heated", str(caught.exception))
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
        self.assertFalse(printer.tick())

    def test_hours_zero_runs_until_stopped(self):
        printer = Printer({1: ASA})
        printer.run("GREASE_BOX_DRY BOX=1 HOURS=0")
        for _ in range(300):
            self.assertTrue(printer.tick())
        self.assertEqual(printer.target(), 45)
        printer.run("GREASE_BOX_DRY_STOP BOX=1")
        self.assertEqual(printer.target(), 0)
        self.assertEqual(printer.state()["active"], 0)
        printer.tick()  # the minute already scheduled still runs, finds nothing to do and stops
        self.assertEqual(printer.target(), 0)
        self.assertFalse(printer.tick())

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
        self.assertFalse(printer.tick())

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


if __name__ == "__main__":
    unittest.main()
