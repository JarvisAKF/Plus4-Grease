"""Tests for the 1.6.0 change list (grease/edits_v160.py), against QIDI's published 1.6.0 files alone
(stock/plus4-1.6.0, QIDITECH/QIDI_PLUS4 at f2b5caf, tag Plus4_V1.6.0)."""
import json
import os
import shutil
import tempfile
import unittest

from grease import core, edits, edits_v160, system
from grease.core import Paths

from test_grease import FakeKlipper, FakeSudo, no_real_commands

HERE = os.path.dirname(os.path.abspath(__file__))
STOCK_DIR = os.path.join(HERE, "..", "stock", "plus4-1.6.0")
FILES = ("printer.cfg", "gcode_macro.cfg")
V160 = edits_v160.FEATURES


def stock_texts():
    texts = {}
    for name in FILES:
        with open(os.path.join(STOCK_DIR, name), "r", encoding="utf-8", newline="") as handle:
            texts[name] = handle.read()
    return texts


def by_id(features, feature_id):
    return next(f for f in features if f.id == feature_id)


class StockTests(unittest.TestCase):
    def test_these_are_qidis_pre_box_files(self):
        texts = stock_texts()
        self.assertNotIn("[include box.cfg]", texts["printer.cfg"])
        self.assertNotIn("Z_TILT_ADJUST", texts["gcode_macro.cfg"])
        self.assertNotIn("runout_", texts["gcode_macro.cfg"])

    def test_every_stock_block_is_there_exactly_once(self):
        texts = stock_texts()
        for feature in V160:
            for edit in feature.edits:
                self.assertIn(edit.file, FILES, feature.id)
                self.assertEqual(len(core.occurrences(texts[edit.file], edit.find)), 1, feature.id)
                self.assertEqual(texts[edit.file].count(edit.replace), 0, feature.id)

    def test_every_change_is_available_and_reverts_to_qidis_exact_text(self):
        original = stock_texts()
        for feature in V160:
            self.assertEqual(core.feature_status(original, feature), "available", feature.id)
            texts = dict(original)
            core.apply_feature(texts, feature)
            self.assertEqual(core.feature_status(texts, feature), "applied", feature.id)
            core.revert_feature(texts, feature)
            self.assertEqual({n: texts[n] for n in FILES}, original, feature.id)

    def test_all_together_round_trip(self):
        texts = stock_texts()
        for feature in V160:
            core.apply_feature(texts, feature)
        for feature in V160:
            self.assertEqual(core.feature_status(texts, feature), "applied", feature.id)
            core.revert_feature(texts, feature)
        self.assertEqual({n: texts[n] for n in FILES}, stock_texts())

    def test_default_changes_only_trim_the_mesh_wait_and_raise_the_probe_speeds(self):
        texts = stock_texts()
        for feature in V160:
            if not feature.option:
                core.apply_feature(texts, feature)
        before, after = stock_texts()["gcode_macro.cfg"].splitlines(), texts["gcode_macro.cfg"].splitlines()
        self.assertEqual({line.strip() for line in before if line not in after}, {"G4 P5000"})
        self.assertEqual({line.strip() for line in after if line not in before}, {"G4 P500"})
        before, after = stock_texts()["printer.cfg"].splitlines(), texts["printer.cfg"].splitlines()
        self.assertEqual([(b, a) for b, a in zip(before, after) if b != a],
                         [("speed: 150", "speed: 300"), ("speed:150", "speed:300")])

    def test_no_box_changes(self):
        ids = [f.id for f in V160]
        self.assertEqual(ids, ["bed_mesh_save_dwell", "z_tilt_probe_moves", "bed_mesh_probe_moves", "board_fan",
                               "balanced_chamber"])
        for feature in V160:
            self.assertFalse(feature.requires or feature.commands or feature.user_files, feature.id)
            for edit in feature.edits:
                self.assertNotIn("box", edit.file)

    def test_ids_and_options_match_the_main_list(self):
        main = {f.id: f for f in edits.FEATURES}
        for feature in V160:
            self.assertIn(feature.id, main)
            self.assertEqual(feature.option, main[feature.id].option, feature.id)
            self.assertEqual(feature.setting, main[feature.id].setting, feature.id)

    def test_the_main_list_on_1_6_0_changes_nothing_else(self):
        # With --any-firmware and an unreadable version, the main list runs here: it must apply only where
        # the 1.6.0 list does, the same way, and leave the Box changes alone.
        texts = stock_texts()
        main = [f for f in edits.FEATURES if all(e.file in FILES for e in f.edits)]
        found = {f.id: core.feature_status(texts, f) for f in main}
        self.assertEqual({i for i, s in found.items() if s == "available"} - {"box_dry_print_start"},
                         {f.id for f in V160})
        self.assertEqual(found["print_start_runout_dwell"], "skipped")
        self.assertEqual(found["box_dry"], "skipped")
        for feature in V160:
            mine, theirs = dict(texts), dict(texts)
            core.apply_feature(mine, feature)
            core.apply_feature(theirs, by_id(edits.FEATURES, feature.id))
            self.assertEqual(mine, theirs, feature.id)


class FirmwareTests(unittest.TestCase):
    def test_1_6_0_gets_its_own_list(self):
        for version in ("V1.6.0", "v1.6.0", "1.6.0"):
            self.assertIs(core.features_for(version), V160)
        for version in ("V2.1.1", "V1.8.2", "V1.8.1", None, "V1.7.1"):
            self.assertIs(core.features_for(version), edits.FEATURES)

    def test_1_6_0_is_accepted_with_a_note(self):
        self.assertIn("V1.6.0", core.supported_soc())
        note = core.firmware_note("V1.6.0")
        self.assertIn("1.6.0 change list", note)
        self.assertIn("Box changes aren't offered", note)


class Printer160(object):
    """A fake printer home with QIDI's stock 1.6.0 files and no Box."""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="plus4-grease-v160-")
        model_file = os.path.join(self.root, "dev_info.txt")
        with open(model_file, "w") as handle:
            handle.write("QIDI@x-plus_4")
        self.paths = Paths(home=os.path.join(self.root, "home"), model_file=model_file)
        os.makedirs(self.paths.config)
        for name in FILES:
            shutil.copyfile(os.path.join(STOCK_DIR, name), self.paths.config_file(name))
        os.makedirs(os.path.join(self.paths.home, "printer_data", "logs"))
        self.lines = []
        system.ROOT, system.RUNNER = os.path.join(self.root, "system"), FakeSudo(os.path.join(self.root, "system"))

    def report(self, line):
        self.lines.append(line)

    def texts(self):
        texts = {}
        for name in FILES:
            with open(self.paths.config_file(name), "r", encoding="utf-8", newline="") as handle:
                texts[name] = handle.read()
        return texts

    def cleanup(self):
        system.RUNNER = no_real_commands
        shutil.rmtree(self.root, ignore_errors=True)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.printer = Printer160()

    def tearDown(self):
        self.printer.cleanup()

    def state(self):
        with open(self.printer.paths.state) as handle:
            return json.load(handle)

    def test_install_status_uninstall(self):
        klipper = FakeKlipper()
        core.install(self.printer.paths, klipper, self.printer.report, firmware="V1.6.0")
        state = self.state()
        self.assertEqual(state["firmware"], "V1.6.0")
        self.assertEqual(state["applied"], ["bed_mesh_probe_moves", "bed_mesh_save_dwell", "usb_event_log",
                                            "z_tilt_probe_moves"])
        self.assertEqual(klipper.restarts, 1)
        # Only the 1.6.0 list was shown: no Box lines.
        self.assertFalse([line for line in self.printer.lines if "Box" in line], self.printer.lines)
        self.printer.lines = []
        core.status(self.printer.paths, self.printer.report)
        self.assertIn("1.6.0 change list", self.printer.lines[0])
        self.assertFalse([line for line in self.printer.lines if "Box" in line], self.printer.lines)
        # The three standard changes and the USB event log.
        self.assertEqual(len([line for line in self.printer.lines if line.strip().startswith("applied")]), 4)
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertEqual(self.printer.texts(), stock_texts())
        self.assertNotIn("firmware", self.state())

    def test_opt_ins_on_1_6_0(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, firmware="V1.6.0",
                     options=["board-fan", "balanced-chamber"])
        self.assertIn("board_fan", self.state()["applied"])
        self.assertIn("balanced_chamber", self.state()["applied"])
        self.assertTrue(os.path.exists(self.printer.paths.config_file(edits.BOARD_FAN_FILE)))
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertEqual(self.printer.texts(), stock_texts())
        self.assertFalse(os.path.exists(self.printer.paths.config_file(edits.BOARD_FAN_FILE)))

    def test_box_switch_does_nothing_on_1_6_0(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, firmware="V1.6.0", options=["box-dry"])
        self.assertNotIn("box_dry", self.state()["applied"])
        self.assertFalse(os.path.exists(self.printer.paths.config_file(edits.BOX_DRY_FILE)))

    def test_dry_run_changes_nothing(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, dry_run=True, firmware="V1.6.0")
        self.assertEqual(self.printer.texts(), stock_texts())
        self.assertFalse(os.path.exists(self.printer.paths.state))
        listed = [line.split()[0] for line in self.printer.lines if line.startswith("  ") and line.split()[0] in
                  ("available", "optional", "skipped", "applied")]
        self.assertEqual(listed, ["available", "available", "available", "optional", "optional", "available"])


class ConfigDiffTests(unittest.TestCase):
    def setUp(self):
        import sys
        sys.path.insert(0, os.path.join(HERE, "..", "tools"))
        import config_diff
        self.config_diff = config_diff
        self.home = tempfile.mkdtemp(prefix="plus4-grease-diff160-")
        self.config = os.path.join(self.home, "printer_data", "config")
        os.makedirs(self.config)
        for name in FILES:
            shutil.copyfile(os.path.join(STOCK_DIR, name), os.path.join(self.config, name))
        self.old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.home

    def tearDown(self):
        if self.old_home is not None:
            os.environ["HOME"] = self.old_home
        shutil.rmtree(self.home, ignore_errors=True)

    def run_diff(self, *args):
        import contextlib
        import io
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = self.config_diff.main(list(args) + [self.config])
        return code, buffer.getvalue()

    def test_stock_1_6_0_against_its_own_files(self):
        code, out = self.run_diff("--firmware", "1.6.0")
        self.assertEqual(code, 0)
        self.assertIn("against QIDI's stock V1.6.0 config", out)
        self.assertIn("printer.cfg:\n  same as stock.", out)
        self.assertIn("gcode_macro.cfg:\n  same as stock.", out)
        self.assertIn("0 differences in all.", out)

    def test_recorded_firmware_and_its_own_edits_taken_out(self):
        texts = stock_texts()
        for feature in V160:
            core.apply_feature(texts, feature)
        for name, text in texts.items():
            with open(os.path.join(self.config, name), "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        core.save_state(core.Paths(home=self.home), {"applied": [f.id for f in V160], "firmware": "V1.6.0"})
        code, out = self.run_diff()
        self.assertIn("against QIDI's stock V1.6.0 config", out)
        self.assertIn("Z tilt: 300 mm/s instead of 150 between probe points", out)
        self.assertIn("0 differences in all.", out)

    def test_unknown_firmware_is_refused(self):
        code, out = self.run_diff("--firmware", "1.4.3")
        self.assertEqual(code, 2)
        self.assertIn("No stock files for firmware V1.4.3", out)


if __name__ == "__main__":
    unittest.main()
