"""Tests for tools/config_diff.py: a made-up converted printer against QIDI's stock 2.1.1 files."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import config_diff  # noqa: E402
from grease import core  # noqa: E402
from grease.edits import FEATURES  # noqa: E402

STOCK_DIR = os.path.join(HERE, "..", "stock", "plus4-2.1.1")
FAKE_SERIAL = "0123456789ABCDEF0123456789ABCDEF"


def stock(name):
    with open(os.path.join(STOCK_DIR, name), "r", encoding="utf-8", newline="") as handle:
        return handle.read()


class ConfigDiffTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="plus4-grease-diff-")
        self.config = os.path.join(self.home, "printer_data", "config")
        os.makedirs(self.config)
        for name in config_diff.COMPARED:
            shutil.copyfile(os.path.join(STOCK_DIR, name), os.path.join(self.config, name))
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.home

    def tearDown(self):
        if self.old_home is not None:
            os.environ["HOME"] = self.old_home
        shutil.rmtree(self.home, ignore_errors=True)

    def write(self, name, text):
        with open(os.path.join(self.config, name), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def run_diff(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            config_diff.main([self.config])
        return buffer.getvalue()

    def test_stock_config_is_the_same_everywhere(self):
        out = self.run_diff()
        self.assertIn("printer.cfg:\n  same as stock.", out)
        self.assertIn("gcode_macro.cfg:\n  same as stock.", out)
        self.assertIn("0 differences in all.", out)

    def test_a_converted_printer(self):
        printer = stock("printer.cfg")
        printer = printer.replace("retries: 2\n", "retries: 5\n").replace("mesh_min:25,10\n", "mesh_min:22,22\n")
        start = printer.index("[smart_effector]")
        end = printer.index("\n[", start + 1)
        printer = printer[:start] + printer[end + 1:]
        printer = printer.replace("[include box.cfg]\n", "[include box.cfg]\n[include beacon.cfg]\n")
        printer = printer.replace("[z_tilt]\n", "[beacon]\nserial: /dev/serial/by-id/usb-Beacon_Beacon_RevH_{}-if00\n"
                                  "x_offset: 0\ny_offset: -18.8\n\n[z_tilt]\n".format(FAKE_SERIAL))
        printer += "#*# [beacon model default]\n#*# model_temp = 47.4\n"
        self.write("printer.cfg", printer)
        macros = stock("gcode_macro.cfg").replace("            _BED_MESH_CALIBRATE PROFILE=default\n",
                                                   "            BED_MESH_CALIBRATE RUNS=2 PROFILE=default\n")
        self.write("gcode_macro.cfg", macros)
        self.write("beacon.cfg", "[gcode_macro BEACON_TEST]\ngcode:\n  M118 hi\n")
        self.write("printer-20261108_032559.cfg", "old")
        out = self.run_diff()
        self.assertIn("  Sections you added:\n    [include beacon.cfg]\n    [beacon]\n", out)
        self.assertIn("serial: /dev/serial/by-id/usb-Beacon_Beacon_RevH_<serial>-if00", out)
        self.assertNotIn(FAKE_SERIAL, out)
        self.assertIn("    [include beacon.cfg]", out)
        self.assertIn("Sections in QIDI's stock config that you don't have:\n    [smart_effector]", out)
        self.assertIn("Changed: [z_tilt]\n        retries: 2 -> 5", out)
        self.assertIn("mesh_min: 25,10 -> 22,22", out)
        self.assertIn("Changed: [gcode_macro G29]", out)
        self.assertIn("-_BED_MESH_CALIBRATE PROFILE=default", out)
        self.assertIn("+BED_MESH_CALIBRATE RUNS=2 PROFILE=default", out)
        self.assertIn("SAVE_CONFIG block: Sections you added:\n    [beacon model default]", out)
        self.assertIn("  beacon.cfg (printer.cfg includes it)", out)
        self.assertIn("...and 1 backup copy (printer-<date>.cfg and the like), left out.", out)
        with open(os.path.join(self.home, [n for n in os.listdir(self.home) if n.startswith("plus4-grease-config")][0])) as f:
            self.assertNotIn(FAKE_SERIAL, f.read())

    def test_plus4_greases_own_edits_are_taken_out(self):
        texts = {"printer.cfg": stock("printer.cfg"), "gcode_macro.cfg": stock("gcode_macro.cfg")}
        for feature in FEATURES:
            core.apply_feature(texts, feature)
        for name, text in texts.items():
            self.write(name, text)  # includes plus4-grease-board-fan.cfg
        paths = core.Paths(home=self.home)
        core.save_state(paths, {"applied": [f.id for f in FEATURES]})
        out = self.run_diff()
        self.assertIn("Plus4 Grease changes taken out before comparing", out)
        self.assertIn("Z tilt: 300 mm/s instead of 150 between probe points", out)
        self.assertIn("0 differences in all.", out)

    def test_pid_moved_to_save_config_is_shown_as_moved(self):
        printer = stock("printer.cfg").replace("pid_Kp=33.555", "#pid_Kp=33.555")
        printer += "#*# [extruder]\n#*# pid_kp = 32.468\n"
        self.write("printer.cfg", printer)
        out = self.run_diff()
        self.assertIn("        pid_kp: 33.555 -> 32.468 (now in the SAVE_CONFIG block)", out)
        self.assertNotIn("removed pid_kp", out)

    def test_inline_comments_and_spacing_dont_count(self):
        printer = stock("printer.cfg").replace("speed: 150\n", "speed : 150   # QIDI's\n", 1)
        printer = printer.replace("mesh_min:25,10\n", "mesh_min: 25, 10\n")
        self.write("printer.cfg", printer)
        self.assertIn("printer.cfg:\n  same as stock.", self.run_diff())


if __name__ == "__main__":
    unittest.main()
