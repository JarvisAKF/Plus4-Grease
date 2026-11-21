"""Tests for Plus4 Grease, run on a computer: python3 -m unittest discover -s tests -v

They run each change against QIDI's stock 2.1.1 gcode_macro.cfg and against hand-changed copies, and run
install and uninstall against a fake printer folder with a fake Klipper.
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from grease import core
from grease.core import GreaseError, Paths
from grease.edits import FEATURES

HERE = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.join(HERE, "stock_gcode_macro_2.1.1.cfg")


def stock_text():
    with open(STOCK, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


class FakeKlipper(object):
    def __init__(self, ready=True):
        self.ready = ready
        self.restarts = 0

    def require_idle(self):
        pass

    def restart_and_wait(self):
        self.restarts += 1
        return self.ready


class Printer(object):
    """A fake printer home with QIDI's stock config and /dev_info.txt."""

    def __init__(self, text=None, model="QIDI@x-plus_4"):
        self.root = tempfile.mkdtemp(prefix="plus4-grease-test-")
        self.model_file = os.path.join(self.root, "dev_info.txt")
        with open(self.model_file, "w") as handle:
            handle.write(model)
        self.paths = Paths(home=os.path.join(self.root, "home"), model_file=self.model_file)
        os.makedirs(self.paths.config)
        self.macro = self.paths.config_file("gcode_macro.cfg")
        with open(self.macro, "w", encoding="utf-8", newline="") as handle:
            handle.write(stock_text() if text is None else text)
        self.lines = []

    def report(self, line):
        self.lines.append(line)

    def macro_text(self):
        with open(self.macro, "r", encoding="utf-8", newline="") as handle:
            return handle.read()

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class EditTests(unittest.TestCase):
    def test_every_stock_block_is_in_qidi_2_1_1_exactly_once(self):
        text = stock_text()
        for feature in FEATURES:
            for edit in feature.edits:
                self.assertEqual(text.count(edit.find), 1, feature.id)
                self.assertEqual(text.count(edit.replace), 0, feature.id)

    def test_changes_only_trim_dwells(self):
        texts = {"gcode_macro.cfg": stock_text()}
        for feature in FEATURES:
            core.apply_feature(texts, feature)
        before, after = stock_text().splitlines(), texts["gcode_macro.cfg"].splitlines()
        removed = [line for line in before if line not in after]
        added = [line for line in after if line not in before]
        self.assertEqual({line.strip() for line in removed}, {"G4 P100", "G4 P5000"})
        self.assertEqual({line.strip() for line in added}, {"G4 P500"})

    def test_apply_then_revert_gives_back_qidis_file(self):
        texts = {"gcode_macro.cfg": stock_text()}
        for feature in FEATURES:
            self.assertEqual(core.feature_status(texts, feature), "available")
            core.apply_feature(texts, feature)
            self.assertEqual(core.feature_status(texts, feature), "applied")
        for feature in FEATURES:
            core.revert_feature(texts, feature)
        self.assertEqual(texts["gcode_macro.cfg"], stock_text())

    def test_hand_changed_macro_is_left_alone(self):
        changed = stock_text().replace("            G4 P100\n", "            G4 P150\n")
        texts = {"gcode_macro.cfg": changed}
        self.assertEqual(core.feature_status(texts, FEATURES[0]), "skipped")

    def test_feature_with_one_changed_block_is_left_alone_whole(self):
        changed = stock_text().replace("            _BED_MESH_CALIBRATE PROFILE=default\n",
                                       "            BEACON_MESH PROFILE=default\n")
        self.assertEqual(core.feature_status({"gcode_macro.cfg": changed}, FEATURES[1]), "skipped")

    def test_crlf_file_is_left_alone(self):
        texts = {"gcode_macro.cfg": stock_text().replace("\n", "\r\n")}
        for feature in FEATURES:
            self.assertEqual(core.feature_status(texts, feature), "skipped")


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.printer = Printer()

    def tearDown(self):
        self.printer.cleanup()

    def test_install_and_uninstall_round_trip(self):
        klipper = FakeKlipper()
        core.install(self.printer.paths, klipper, self.printer.report)
        self.assertNotEqual(self.printer.macro_text(), stock_text())
        self.assertEqual(sorted(core.load_state(self.printer.paths)["applied"]),
                         sorted(f.id for f in FEATURES))
        core.uninstall(self.printer.paths, klipper, self.printer.report)
        self.assertEqual(self.printer.macro_text(), stock_text())
        self.assertEqual(klipper.restarts, 2)

    def test_install_keeps_a_backup_of_qidis_file(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        folder = core.load_state(self.printer.paths)["last_backup"]
        with open(os.path.join(folder, "gcode_macro.cfg"), "r", encoding="utf-8", newline="") as handle:
            self.assertEqual(handle.read(), stock_text())

    def test_dry_run_changes_nothing(self):
        klipper = FakeKlipper()
        core.install(self.printer.paths, klipper, self.printer.report, dry_run=True)
        self.assertEqual(self.printer.macro_text(), stock_text())
        self.assertFalse(os.path.exists(self.printer.paths.state_dir))
        self.assertEqual(klipper.restarts, 0)

    def test_klipper_failing_to_start_puts_everything_back(self):
        klipper = FakeKlipper(ready=False)
        with self.assertRaises(GreaseError):
            core.install(self.printer.paths, klipper, self.printer.report)
        self.assertEqual(self.printer.macro_text(), stock_text())
        self.assertEqual(core.load_state(self.printer.paths).get("applied", []), [])

    def test_second_install_changes_nothing(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        after_first = self.printer.macro_text()
        klipper = FakeKlipper()
        core.install(self.printer.paths, klipper, self.printer.report)
        self.assertEqual(self.printer.macro_text(), after_first)
        self.assertEqual(klipper.restarts, 0)


class PrinterCheckTests(unittest.TestCase):
    def test_refuses_other_printers(self):
        printer = Printer(model="QIDI@x-max_3")
        try:
            with mock.patch("os.geteuid", return_value=1000):
                with self.assertRaises(GreaseError):
                    core.check_printer(printer.paths, "V2.1.1")
        finally:
            printer.cleanup()

    def test_refuses_root(self):
        printer = Printer()
        try:
            with mock.patch("os.geteuid", return_value=0):
                with self.assertRaises(GreaseError):
                    core.check_printer(printer.paths, "V2.1.1")
        finally:
            printer.cleanup()

    def test_refuses_unknown_firmware_unless_asked(self):
        printer = Printer()
        try:
            with mock.patch("os.geteuid", return_value=1000):
                with self.assertRaises(GreaseError):
                    core.check_printer(printer.paths, "V1.8.2")
                core.check_printer(printer.paths, "V1.8.2", any_firmware=True)
                core.check_printer(printer.paths, "V2.1.1")
        finally:
            printer.cleanup()

    def test_reads_qidis_version_file(self):
        text = "[version]\nmcu             = V0.12.0\nui              = V211\nsoc             = V2.1.1"
        self.assertEqual(core.parse_soc_version(text), "V2.1.1")


if __name__ == "__main__":
    unittest.main()
