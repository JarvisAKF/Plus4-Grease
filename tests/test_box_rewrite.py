"""QIDI's box_detect rewrites box.cfg from its Box templates through Python's configparser (box_detect.so
imports ConfigParser, shutil and filecmp; seen on a V2.1.1 Plus 4 right after a Klipper restart). These tests
replay that rewrite with the printer's Python 3.7 section rule and check the cool-down lock's include
survives it, that Klipper's include rule then finds the lock file, and that 0.13.0/0.13.1's include, which
that rewrite cut to '[include plus4-grease-box-loc[k]', is updated and removed properly."""
import configparser
import glob
import os
import re
import shutil
import unittest

from grease import core, edits

from test_grease import FakeKlipper, Printer, stock_text

FAKE_SERIAL = "/dev/serial/by-id/usb-Klipper_stm32f401xc_TEST-if00"


class QidiParser(configparser.ConfigParser):
    # Python 3.7's section pattern: a section name ends at its first ']'.
    SECTCRE = re.compile(r"\[(?P<header>[^]]+)\]")


def box_detect(template, box_cfg):
    """What QIDI's box_detect does to box.cfg: copy the template, read it with ConfigParser, fill in the Box
    board's serial, write it back."""
    shutil.copyfile(template, box_cfg)
    parser = QidiParser(delimiters=(":",))
    parser.read(box_cfg)
    for section in parser.sections():
        if section.startswith("mcu mcu_box"):
            parser.set(section, "serial", FAKE_SERIAL)
    with open(box_cfg, "w") as handle:
        parser.write(handle)


def klipper_includes(path):
    """The files Klipper would include from path, by QIDI's configfile._resolve_include rule: a glob, where
    no match is fine for a pattern but an error for a plain name."""
    found = []
    with open(path) as handle:
        for line in handle:
            line = line.split("#")[0].strip()
            match = re.match(r"^\[include (.*)\]$", line)
            if not match:
                continue
            pattern = os.path.join(os.path.dirname(path), match.group(1).strip())
            names = glob.glob(pattern)
            if not names and not glob.has_magic(pattern):
                raise AssertionError("Klipper: Include file '{}' does not exist".format(pattern))
            found += [os.path.basename(n) for n in sorted(names)]
    return found


OLD_TEMPLATE_BLOCK = edits.BOX_LOCK_OLDER[0]


class RewriteTests(unittest.TestCase):
    def setUp(self):
        self.printer = Printer()
        self.box = self.printer.paths.config_file("box.cfg")
        open(self.printer.paths.config_file("box1.cfg"), "w").close()

    def tearDown(self):
        self.printer.cleanup()

    def lock_row(self):
        _, rows = core.plan(self.printer.paths)
        return next(r for r in rows if r.feature.id == "box_dry_lock")

    def test_the_replay_matches_what_the_printer_wrote(self):
        # The owner's box.cfg after 0.13.1's install and QIDI's rewrite started like this (serial left out).
        template = os.path.join(self.printer.root, "old_template")
        with open(template, "w") as handle:
            handle.write(stock_text("~/cfg_with_1").replace("[include box1.cfg]\n", OLD_TEMPLATE_BLOCK, 1))
        box_detect(template, self.box)
        text = self.printer.text("box.cfg")
        self.assertTrue(text.startswith("[include box1.cfg]\n\n[include plus4-grease-box-loc[k]\n\n[box_extras]\n"
                                        "b_button_pin : ^mcu_box1:PB1\n"), text[:200])
        self.assertIn("debounce_us : 50\nrunout_gcode : \n\t{% set slot_sync", text)
        self.assertEqual(klipper_includes(self.box), ["box1.cfg"])  # the lock isn't loaded

    def test_the_include_survives_the_rewrite_for_one_to_four_boxes(self):
        for n in range(1, 5):
            with self.subTest(boxes=n):
                printer = Printer()
                try:
                    template = printer.paths.file("~/cfg_with_{}".format(n))
                    box = printer.paths.config_file("box.cfg")
                    shutil.copyfile(template, box)
                    for b in range(1, n + 1):
                        open(printer.paths.config_file("box{}.cfg".format(b)), "w").close()
                    core.install(printer.paths, FakeKlipper(), printer.report, options=["box-dry"])
                    box_detect(template, box)
                    _, rows = core.plan(printer.paths)
                    row = next(r for r in rows if r.feature.id == "box_dry_lock")
                    self.assertEqual(row.status, "applied")
                    self.assertIn("plus4-grease-box-lock.cfg", klipper_includes(box))
                    self.assertEqual(klipper_includes(box)[0], "box1.cfg")
                    core.uninstall(printer.paths, FakeKlipper(), printer.report)
                    self.assertEqual(printer.text("~/cfg_with_{}".format(n)), stock_text("~/cfg_with_{}".format(n)))
                    self.assertNotIn("box-loc", printer.text("box.cfg"))
                    box_detect(template, box)
                    self.assertNotIn("box-loc", printer.text("box.cfg"))
                finally:
                    printer.cleanup()

    def test_a_missing_lock_file_is_fine_for_klipper(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry"])
        box_detect(self.printer.paths.file("~/cfg_with_1"), self.box)
        os.unlink(self.printer.paths.config_file("plus4-grease-box-lock.cfg"))
        self.assertEqual(klipper_includes(self.box), ["box1.cfg"])

    def owners_0_13_1_printer(self):
        """The owner's printer after 0.13.1: templates with the old block, box.cfg rewritten by QIDI."""
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry"])
        for n in range(1, 5):
            name = "~/cfg_with_{}".format(n)
            with open(self.printer.paths.file(name), "w", newline="") as handle:
                handle.write(stock_text(name).replace("[include box1.cfg]\n", OLD_TEMPLATE_BLOCK, 1))
        box_detect(self.printer.paths.file("~/cfg_with_1"), self.box)
        self.assertIn("[include plus4-grease-box-loc[k]\n", self.printer.text("box.cfg"))

    def test_0_13_1_lock_shows_as_update_and_install_fixes_it(self):
        self.owners_0_13_1_printer()
        self.assertEqual(self.lock_row().status, "update")
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertEqual(self.lock_row().status, "applied")
        for n in range(1, 5):
            name = "~/cfg_with_{}".format(n)
            self.assertEqual(self.printer.text(name),
                             stock_text(name).replace("[include box1.cfg]\n",
                                                      "[include box1.cfg]\n\n[include plus4-grease-box-loc?.cfg]\n", 1))
        self.assertNotIn("loc[k]", self.printer.text("box.cfg"))
        box_detect(self.printer.paths.file("~/cfg_with_1"), self.box)
        self.assertEqual(self.lock_row().status, "applied")
        self.assertIn("plus4-grease-box-lock.cfg", klipper_includes(self.box))

    def test_0_13_1_lock_comes_out_on_uninstall(self):
        self.owners_0_13_1_printer()
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        for n in range(1, 5):
            name = "~/cfg_with_{}".format(n)
            self.assertEqual(self.printer.text(name), stock_text(name))
        self.assertNotIn("box-loc", self.printer.text("box.cfg"))
        self.assertFalse(self.printer.has("plus4-grease-box-lock.cfg"))

    def test_the_include_line_is_configparser_safe(self):
        self.assertNotIn("]", edits.BOX_LOCK_INCLUDE[1:-2])
        self.assertNotIn("#", edits.BOX_LOCK_INCLUDE)


if __name__ == "__main__":
    unittest.main()
