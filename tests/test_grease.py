"""Tests for Plus4 Grease, run on a computer: python3 -m unittest discover -s tests -v

They run each change against QIDI's stock 2.1.1 gcode_macro.cfg and printer.cfg and against hand-changed
copies, and run install and uninstall against a fake printer folder with a fake Klipper.
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from grease import core, edits, system
from grease.core import GreaseError, Paths
from grease.edits import FEATURES


def no_real_commands(command, **kwargs):
    raise AssertionError("a test tried to run a real command: {}".format(command))


# Nothing in these tests may touch the real /etc or run sudo. Printer() swaps in a scratch root and a fake.
system.ROOT = tempfile.mkdtemp(prefix="plus4-grease-no-root-")
system.RUNNER = no_real_commands
DEFAULTS = [f for f in FEATURES if not f.option]
OPT_INS = [f for f in FEATURES if f.option]
ALL_IDS = sorted([f.id for f in DEFAULTS] + ["usb_event_log"])


class FakeSudo(object):
    """Does what the installer asks sudo to do, inside a scratch root."""

    def __init__(self, root, fail=(), fail_targets=()):
        self.root, self.fail, self.fail_targets, self.calls = root, set(fail), set(fail_targets), []

    def where(self, path):
        if path.startswith(tempfile.gettempdir()):  # a fake printer's home folder (QIDI's Box templates)
            return path
        return os.path.join(self.root, path.lstrip("/"))

    def __call__(self, command, **kwargs):
        assert command[0] == "sudo", command
        self.calls.append(command[1:])
        args = command[1:]
        if args[0] in self.fail or any(args[-1].endswith(t) for t in self.fail_targets):
            return subprocess.CompletedProcess(command, 1, stdout="permission denied")
        if args[0] == "install":
            mode, source, target = args[args.index("-m") + 1], args[-2], self.where(args[-1])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(source, target)
            os.chmod(target, int(mode, 8))
        elif args[0] == "rm":
            if os.path.exists(self.where(args[-1])):
                os.unlink(self.where(args[-1]))
        elif args[0] == "rmdir":
            try:
                os.rmdir(self.where(args[-1]))
            except OSError:
                return subprocess.CompletedProcess(command, 1, stdout="not empty")
        elif args[0] not in ("udevadm", system.SCRIPT):
            raise AssertionError("unexpected sudo command {}".format(args))
        return subprocess.CompletedProcess(command, 0, stdout="")

HERE = os.path.dirname(os.path.abspath(__file__))
STOCK_DIR = os.path.join(HERE, "..", "stock", "plus4-2.1.1")
# A printer with one Box: QIDI copies cfg_with_1 to box.cfg. The templates are in the home folder.
STOCK = {"gcode_macro.cfg": os.path.join(STOCK_DIR, "gcode_macro.cfg"),
         "printer.cfg": os.path.join(STOCK_DIR, "printer.cfg"),
         "box.cfg": os.path.join(STOCK_DIR, "cfg_with_1")}
STOCK.update({"~/cfg_with_{}".format(n): os.path.join(STOCK_DIR, "cfg_with_{}".format(n)) for n in range(1, 5)})
NO_BOX = os.path.join(STOCK_DIR, "cfg_with_0")


def stock_text(name="gcode_macro.cfg"):
    with open(STOCK[name], "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def stock_texts():
    return {name: stock_text(name) for name in STOCK}


def by_id(feature_id):
    return next(f for f in FEATURES if f.id == feature_id)


QIDI_COMMANDS = {"E_LOAD", "E_BOX", "E_UNLOAD", "EXTRUDER_LOAD", "EXTRUDER_UNLOAD", "PRINT_START"}


class FakeKlipper(object):
    def __init__(self, ready=True, loaded=None, commands=QIDI_COMMANDS):
        self.ready = ready
        self.restarts = 0
        self.loaded = loaded
        self.have = commands

    def settings(self):
        return self.loaded

    def commands(self):
        return None if self.have is None else set(self.have)

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
        for name in STOCK:
            with open(self.paths.file(name), "w", encoding="utf-8", newline="") as handle:
                handle.write(text if name == "gcode_macro.cfg" and text is not None else stock_text(name))
            if core.is_home(name):
                os.chmod(self.paths.file(name), 0o744)
        os.makedirs(os.path.join(self.paths.home, "printer_data", "logs"))
        self.lines = []
        self.system_root = os.path.join(self.root, "system")
        self.sudo = FakeSudo(self.system_root)
        system.ROOT, system.RUNNER = self.system_root, self.sudo

    def report(self, line):
        self.lines.append(line)

    def macro_text(self):
        return self.text("gcode_macro.cfg")

    def text(self, name):
        with open(self.paths.file(name), "r", encoding="utf-8", newline="") as handle:
            return handle.read()

    def has(self, name):
        return os.path.exists(self.paths.file(name))

    def cleanup(self):
        system.RUNNER = no_real_commands
        shutil.rmtree(self.root, ignore_errors=True)


class EditTests(unittest.TestCase):
    def test_every_stock_block_is_in_qidi_2_1_1_exactly_once(self):
        texts = stock_texts()
        for feature in FEATURES:
            for edit in feature.edits:
                self.assertEqual(texts[edit.file].count(edit.find), 1, feature.id)
                self.assertEqual(len(core.occurrences(texts[edit.file], edit.find)), 1, feature.id)
                self.assertEqual(texts[edit.file].count(edit.replace), 0, feature.id)

    def test_a_block_in_the_middle_of_a_line_doesnt_count(self):
        self.assertEqual(core.occurrences("a\n#[x]\ny\n[x]\ny\n", "[x]\ny\n"), [9])
        texts = stock_texts()
        texts["printer.cfg"] = texts["printer.cfg"].replace("[controller_fan board_fan]\n",
                                                            "#[controller_fan board_fan]\n")
        self.assertEqual(core.feature_status(texts, [f for f in FEATURES if f.id == "board_fan"][0]),
                         "skipped")

    def test_macro_changes_only_trim_dwells(self):
        texts = stock_texts()
        for feature in DEFAULTS:
            core.apply_feature(texts, feature)
        before, after = stock_text().splitlines(), texts["gcode_macro.cfg"].splitlines()
        removed = [line for line in before if line not in after]
        added = [line for line in after if line not in before]
        self.assertEqual({line.strip() for line in removed}, {"G4 P100", "G4 P5000"})
        self.assertEqual({line.strip() for line in added}, {"G4 P500"})

    def test_printer_cfg_changes_only_the_z_tilt_and_bed_mesh_speeds(self):
        texts = stock_texts()
        for feature in DEFAULTS:
            core.apply_feature(texts, feature)
        before, after = stock_text("printer.cfg").splitlines(), texts["printer.cfg"].splitlines()
        self.assertEqual(len(before), len(after))
        changed = [(b, a) for b, a in zip(before, after) if b != a]
        self.assertEqual(changed, [("speed: 150", "speed: 300"), ("speed:150", "speed:300")])
        section = None
        for b, a in zip(before, after):
            if b.startswith("["):
                section = b
            if b != a:
                self.assertIn(section, ("[z_tilt]", "[bed_mesh]"))

    def test_apply_then_revert_gives_back_qidis_files(self):
        texts = stock_texts()
        for feature in FEATURES:
            self.assertEqual(core.feature_status(texts, feature), "available")
            core.apply_feature(texts, feature)
            self.assertEqual(core.feature_status(texts, feature), "applied")
        for feature in FEATURES:
            core.revert_feature(texts, feature)
        self.assertEqual({n: t for n, t in texts.items() if t is not None}, stock_texts())

    def test_own_probe_speed_is_left_alone(self):
        texts = stock_texts()
        texts["printer.cfg"] = texts["printer.cfg"].replace("speed:150\n", "speed:250\n")
        self.assertEqual(core.feature_status(texts, by_id("bed_mesh_probe_moves")), "skipped")
        self.assertEqual(core.feature_status(texts, by_id("z_tilt_probe_moves")), "available")

    def test_saved_mesh_in_the_autosave_block_doesnt_count(self):
        texts = stock_texts()
        texts["printer.cfg"] += "#*# [bed_mesh default]\n#*# version = 1\n"
        for feature_id in ("bed_mesh_probe_moves", "z_tilt_probe_moves"):
            self.assertEqual(core.feature_status(texts, by_id(feature_id)), "available")

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
        for name in ("gcode_macro.cfg", "printer.cfg"):
            self.assertNotEqual(self.printer.text(name), stock_text(name), name)
        self.assertEqual(sorted(core.load_state(self.printer.paths)["applied"]), ALL_IDS)
        core.uninstall(self.printer.paths, klipper, self.printer.report)
        for name in STOCK:
            self.assertEqual(self.printer.text(name), stock_text(name), name)
        self.assertEqual(klipper.restarts, 2)

    def test_install_keeps_a_backup_of_qidis_files(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry"])
        folder = core.load_state(self.printer.paths)["last_backup"]
        for name in STOCK:
            with open(os.path.join(folder, core.backup_name(name)), "r", encoding="utf-8", newline="") as handle:
                self.assertEqual(handle.read(), stock_text(name), name)

    def test_dry_run_changes_nothing(self):
        klipper = FakeKlipper()
        core.install(self.printer.paths, klipper, self.printer.report, dry_run=True)
        for name in STOCK:
            self.assertEqual(self.printer.text(name), stock_text(name), name)
        self.assertFalse(os.path.exists(self.printer.paths.state_dir))
        self.assertEqual(klipper.restarts, 0)
        self.assertEqual(self.printer.sudo.calls, [])
        self.assertTrue(any("available  USB event log" in line for line in self.printer.lines))

    def test_klipper_failing_to_start_puts_everything_back(self):
        klipper = FakeKlipper(ready=False)
        with self.assertRaises(GreaseError):
            core.install(self.printer.paths, klipper, self.printer.report)
        for name in STOCK:
            self.assertEqual(self.printer.text(name), stock_text(name), name)
        self.assertEqual(core.load_state(self.printer.paths).get("applied", []), [])
        self.assertEqual(system.status(self.printer.paths), "available")

    def test_upgrade_from_0_1_adds_the_new_changes_and_keeps_the_old(self):
        texts = {"gcode_macro.cfg": self.printer.macro_text()}
        core.apply_feature(texts, by_id("print_start_runout_dwell"))
        with open(self.printer.macro, "w", encoding="utf-8", newline="") as handle:
            handle.write(texts["gcode_macro.cfg"])
        core.save_state(self.printer.paths, {"version": "0.1.0", "applied": ["print_start_runout_dwell"]})
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertEqual(sorted(core.load_state(self.printer.paths)["applied"]), ALL_IDS)
        self.assertIn("speed: 300\n", self.printer.text("printer.cfg"))

    def write_printer_cfg(self, text):
        with open(self.printer.paths.config_file("printer.cfg"), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)

    def test_own_speed_needs_the_switch_and_comes_back_on_uninstall(self):
        own = stock_text("printer.cfg").replace("[bed_mesh]\nspeed:150\n", "[bed_mesh]\nspeed: 200  # mine\n")
        self.write_printer_cfg(own)
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, dry_run=True)
        self.assertTrue(any("--replace-own-speeds" in line for line in self.printer.lines))
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertNotIn("bed_mesh_probe_moves", core.load_state(self.printer.paths)["applied"])
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, replace_own=True)
        state = core.load_state(self.printer.paths)
        self.assertIn("bed_mesh_probe_moves", state["applied"])
        self.assertEqual(state["own_values"]["bed_mesh_probe_moves"]["was"], "speed: 200  # mine under [bed_mesh]")
        self.assertIn("[bed_mesh]\nspeed: 300  # mine\n", self.printer.text("printer.cfg"))
        self.printer.lines = []
        core.status(self.printer.paths, self.printer.report)
        self.assertTrue(any("replacing your speed: 200" in line for line in self.printer.lines))
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertEqual(self.printer.text("printer.cfg"), own)
        self.assertNotIn("own_values", core.load_state(self.printer.paths))

    def test_missing_speed_line_is_added_and_taken_out_again(self):
        own = stock_text("printer.cfg").replace("[z_tilt]\n", "[z_tilt]\n", 1).replace(
            "\nspeed: 150\nhorizontal_move_z: 5\n", "\nhorizontal_move_z: 5\n")
        self.write_printer_cfg(own)
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, replace_own=True)
        self.assertIn("[z_tilt]\nspeed: 300\nz_positions:\n", self.printer.text("printer.cfg"))
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertEqual(self.printer.text("printer.cfg"), own)

    def test_section_twice_is_left_alone_even_with_the_switch(self):
        own = stock_text("printer.cfg").replace("[bed_mesh]\nspeed:150\n", "[bed_mesh]\nspeed: 200\n") \
            + "\n[bed_mesh]\nspeed: 250\n"
        self.write_printer_cfg(own)
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, replace_own=True)
        self.assertNotIn("bed_mesh_probe_moves", core.load_state(self.printer.paths)["applied"])
        self.assertIn("[bed_mesh]\nspeed: 200\n", self.printer.text("printer.cfg"))

    def test_own_speed_already_300_is_left_alone(self):
        self.write_printer_cfg(stock_text("printer.cfg").replace("[bed_mesh]\nspeed:150\n", "[bed_mesh]\nspeed: 300.0\n"))
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, replace_own=True)
        self.assertNotIn("bed_mesh_probe_moves", core.load_state(self.printer.paths)["applied"])
        self.assertTrue(any("already has 300" in line for line in self.printer.lines))

    def test_says_so_when_klipper_loaded_another_value(self):
        loaded = {"z_tilt": {"speed": 300.0}, "bed_mesh": {"speed": 150.0}}
        core.install(self.printer.paths, FakeKlipper(loaded=loaded), self.printer.report)
        self.assertTrue(any("Klipper is using speed = 300 under [z_tilt]" in line for line in self.printer.lines))
        self.assertTrue(any("Note: Klipper is using speed = 150.0 under [bed_mesh], not 300" in line
                            for line in self.printer.lines))

    def test_beacon_printer_with_its_own_bed_mesh_gets_the_rest(self):
        path = self.printer.paths.config_file("printer.cfg")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(stock_text("printer.cfg").replace("[bed_mesh]\nspeed:150\n", "[bed_mesh]\nspeed: 200\n"))
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        applied = core.load_state(self.printer.paths)["applied"]
        self.assertIn("z_tilt_probe_moves", applied)
        self.assertNotIn("bed_mesh_probe_moves", applied)
        self.assertIn("[bed_mesh]\nspeed: 200\n", self.printer.text("printer.cfg"))

    def test_second_install_changes_nothing(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        after_first = self.printer.macro_text()
        klipper = FakeKlipper()
        core.install(self.printer.paths, klipper, self.printer.report)
        self.assertEqual(self.printer.macro_text(), after_first)
        self.assertEqual(klipper.restarts, 0)


class OptInTests(unittest.TestCase):
    def setUp(self):
        self.printer = Printer()

    def tearDown(self):
        self.printer.cleanup()

    def fan_file(self):
        return self.printer.paths.config_file("plus4-grease-board-fan.cfg")

    def test_off_unless_asked(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        applied = core.load_state(self.printer.paths)["applied"]
        self.assertNotIn("board_fan", applied)
        self.assertNotIn("balanced_chamber", applied)
        self.assertFalse(os.path.exists(self.fan_file()))
        self.assertTrue(any("Off unless you ask: add --board-fan" in line for line in self.printer.lines))
        self.printer.lines = []
        core.status(self.printer.paths, self.printer.report)
        self.assertTrue(any(line.startswith("  optional") and "Board fan" in line for line in self.printer.lines))

    def test_board_fan_in_and_out(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["board-fan"])
        text = self.printer.text("printer.cfg")
        self.assertNotIn("\n[controller_fan board_fan]\n", text)
        self.assertNotIn("[controller_fan board_fan]", text)
        self.assertIn("\n[include plus4-grease-board-fan.cfg]\n", text)
        with open(self.fan_file()) as handle:
            fan = handle.read()
        self.assertIn("[fan_generic board_fan]\npin: U_1:PC4\n", fan)
        self.assertIn("[delayed_gcode _BOARD_FAN_LOOP]", fan)
        self.assertIn("sensor_mcu: U_1", fan)
        self.assertIn("board_fan", core.load_state(self.printer.paths)["applied"])
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertFalse(os.path.exists(self.fan_file()))
        self.assertEqual(self.printer.text("printer.cfg"), stock_text("printer.cfg"))

    def test_balanced_chamber_in_and_out(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["balanced-chamber"])
        text = self.printer.text("printer.cfg")
        self.assertIn("[temperature_sensor chamber_probe]\nsensor_type:NTC 100K MGB18-104F39050L32\n"
                      "sensor_pin:U_1:PA1\n", text)
        self.assertIn("sensor_list: temperature_sensor GD32, temperature_sensor chamber_probe, "
                      "temperature_sensor GD32, temperature_sensor GD32\n", text)
        self.assertIn("max_power:0.6\n", text)
        self.assertIn("max_temp:80\n", text)
        for gone in ("target_min_temp", "target_max_temp", "heat_with_heater_bed"):
            self.assertNotIn(gone, text)
        self.assertIn("[temperature_sensor Chamber_Thermal_Protection_Sensor]\nsensor_type:NTC 100K "
                      "MGB18-104F39050L32\nsensor_pin:U_1:PC2\nmin_temp:-100\nmax_temp:140\n", text)
        self.assertEqual(text.count("[temperature_sensor GD32]"), 1)
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertEqual(self.printer.text("printer.cfg"), stock_text("printer.cfg"))

    def test_box_dry_in_and_out(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry"])
        text = self.printer.text("printer.cfg")
        self.assertIn("[include KAMP_Settings.cfg]\n# Plus4 Grease (--box-dry): Box drying macros.\n"
                      "[include plus4-grease-box-dry.cfg]\n[include box.cfg]\n", text)
        self.assertEqual(text.count("[include box.cfg]"), 1)
        dry = self.printer.paths.config_file("plus4-grease-box-dry.cfg")
        with open(dry) as handle:
            self.assertIn("[gcode_macro GREASE_BOX_DRY]", handle.read())
        self.assertIn("box_dry", core.load_state(self.printer.paths)["applied"])
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertFalse(os.path.exists(dry))
        self.assertEqual(self.printer.text("printer.cfg"), stock_text("printer.cfg"))

    def test_box_dry_from_0_9_0_is_updated_without_asking_again(self):
        # 0.9.0 wrote macros named PLUS4_BOX_DRY, which Klipper reads as PLUS4; this is that file, by its hash.
        feature = next(f for f in core.FEATURES if f.id == "box_dry")
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry"])
        dry = self.printer.paths.config_file("plus4-grease-box-dry.cfg")
        old = feature.files[0][1].replace("GREASE_BOX_DRY", "PLUS4_BOX_DRY")
        with open(dry, "w", newline="") as handle:
            handle.write(old)
        with mock.patch.object(core, "FEATURES", [f._replace(replaces=((
                "plus4-grease-box-dry.cfg", hashlib.sha256(old.encode("utf-8")).hexdigest()),))
                if f.id == "box_dry" else f for f in core.FEATURES]):
            self.printer.lines = []
            core.status(self.printer.paths, self.printer.report)
            self.assertTrue(any(line.startswith("  update") and "Box drying" in line for line in self.printer.lines))
            core.install(self.printer.paths, FakeKlipper(), self.printer.report)
            with open(dry) as handle:
                self.assertEqual(handle.read(), feature.files[0][1])
            self.assertIn("box_dry", core.load_state(self.printer.paths)["applied"])
            self.assertEqual(self.printer.text("printer.cfg").count("[include plus4-grease-box-dry.cfg]"), 1)
            with open(dry, "w", newline="") as handle:
                handle.write(old)
            core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertFalse(os.path.exists(dry))
        self.assertEqual(self.printer.text("printer.cfg"), stock_text("printer.cfg"))

    def lock_parts(self):
        return ["box.cfg"] + ["~/cfg_with_{}".format(n) for n in range(1, 5)]

    def test_box_dry_adds_the_lock_print_start_wait_and_settings(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry"])
        include = "[include box1.cfg]\n# Plus4 Grease (--box-dry): Box cool-down lock. A pattern: nothing if the "
        for name in self.lock_parts():
            self.assertEqual(self.printer.text(name).count(include), 1, name)
            self.assertEqual(self.printer.text(name).replace(
                "# Plus4 Grease (--box-dry): Box cool-down lock. A pattern: nothing if the file is gone.\n"
                "[include plus4-grease-box-loc[k].cfg]\n", ""), stock_text(name), name)
        for n in range(1, 5):
            self.assertEqual(os.stat(self.printer.paths.file("~/cfg_with_{}".format(n))).st_mode & 0o777, 0o744)
        written = [c[-1] for c in self.printer.sudo.calls if c[0] == "install" and "cfg_with" in c[-1]]
        self.assertEqual(sorted(os.path.basename(w) for w in written), ["cfg_with_1", "cfg_with_2", "cfg_with_3",
                                                                       "cfg_with_4"])
        self.assertIn("    _GREASE_BOX_PRINT_CHECK\n    {% endif %}\n    AUTOTUNE_SHAPERS\n",
                      self.printer.text("gcode_macro.cfg"))
        self.assertEqual(self.printer.text("plus4-grease-box-lock.cfg"), edits.BOX_LOCK_CFG)
        self.assertEqual(self.printer.text("plus4-grease-box-dry-settings.cfg"), edits.BOX_SETTINGS_CFG)
        applied = core.load_state(self.printer.paths)["applied"]
        for feature_id in ("box_dry", "box_dry_print_start", "box_dry_lock"):
            self.assertIn(feature_id, applied)
        self.printer.lines = []
        core.status(self.printer.paths, self.printer.report)
        self.assertTrue(any(line.startswith("  applied    Box drying") and line.endswith(
            "\n             PLA/TPU drying off in plus4-grease-box-dry-settings.cfg (GREASE_BOX_DRY_SETTINGS "
            "shows all the settings)") for line in self.printer.lines))
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        for name in STOCK:
            self.assertEqual(self.printer.text(name), stock_text(name), name)
        for name in ("plus4-grease-box-dry.cfg", "plus4-grease-box-lock.cfg", "plus4-grease-box-dry-settings.cfg"):
            self.assertFalse(self.printer.has(name), name)

    def test_box_dry_pla_turns_pla_drying_on(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry", "box-dry-pla"])
        self.assertIn(edits.PLA_ON, self.printer.text("plus4-grease-box-dry-settings.cfg"))
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertFalse(self.printer.has("plus4-grease-box-dry-settings.cfg"))

    def test_box_dry_pla_later_switches_it_on_and_restarts(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry"])
        klipper = FakeKlipper()
        self.printer.lines = []
        core.install(self.printer.paths, klipper, self.printer.report, options=["box-dry", "box-dry-pla"])
        self.assertIn(edits.PLA_ON, self.printer.text("plus4-grease-box-dry-settings.cfg"))
        self.assertIn("Turned PLA/TPU drying on in plus4-grease-box-dry-settings.cfg.", self.printer.lines)
        self.assertEqual(klipper.restarts, 1)
        self.printer.lines = []
        core.install(self.printer.paths, klipper, self.printer.report, options=["box-dry", "box-dry-pla"])
        self.assertIn("Nothing to change.", self.printer.lines)

    def test_your_settings_are_never_overwritten_and_kept_on_uninstall(self):
        mine = edits.BOX_SETTINGS_CFG.replace("variable_unlock_temp: 35", "variable_unlock_temp: 40")
        with open(self.printer.paths.config_file("plus4-grease-box-dry-settings.cfg"), "w") as handle:
            handle.write(mine)
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry"])
        self.assertEqual(self.printer.text("plus4-grease-box-dry-settings.cfg"), mine)
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertEqual(self.printer.text("plus4-grease-box-dry-settings.cfg"), mine)
        self.assertTrue(any(line.startswith("  kept       plus4-grease-box-dry-settings.cfg")
                            for line in self.printer.lines))

    def test_box_dry_pla_leaves_a_settings_file_it_cant_read(self):
        mine = edits.BOX_SETTINGS_CFG.replace(edits.PLA_OFF, "variable_pla_drying: 0\n")
        with open(self.printer.paths.config_file("plus4-grease-box-dry-settings.cfg"), "w") as handle:
            handle.write(mine)
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry", "box-dry-pla"])
        self.assertEqual(self.printer.text("plus4-grease-box-dry-settings.cfg"), mine)
        self.assertTrue(any("Set variable_pla_drying: True there yourself." in line for line in self.printer.lines))

    def test_update_from_0_12_brings_the_new_parts_without_asking_again(self):
        feature = by_id("box_dry")
        printer_cfg = stock_text("printer.cfg")
        texts = {"printer.cfg": printer_cfg}
        core.apply_feature(texts, feature)
        with open(self.printer.paths.config_file("printer.cfg"), "w", newline="") as handle:
            handle.write(texts["printer.cfg"])
        old = feature.files[0][1].split("[gcode_macro _GREASE_BOX_LOCKED]")[0]
        with open(self.printer.paths.config_file("plus4-grease-box-dry.cfg"), "w", newline="") as handle:
            handle.write(old)
        older = feature.replaces + (("plus4-grease-box-dry.cfg", hashlib.sha256(old.encode("utf-8")).hexdigest()),)
        with mock.patch.object(core, "FEATURES", [f._replace(replaces=older) if f.id == "box_dry" else f
                                                  for f in core.FEATURES]):
            core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertEqual(self.printer.text("plus4-grease-box-dry.cfg"), feature.files[0][1])
        self.assertTrue(self.printer.has("plus4-grease-box-lock.cfg"))
        self.assertTrue(self.printer.has("plus4-grease-box-dry-settings.cfg"))
        self.assertIn("_GREASE_BOX_PRINT_CHECK", self.printer.text("gcode_macro.cfg"))
        self.assertIn("plus4-grease-box-loc[k].cfg", self.printer.text("~/cfg_with_2"))

    def test_0_12s_file_is_one_box_dry_updates(self):
        self.assertIn(("plus4-grease-box-dry.cfg", "4062df48c530b28ed10d0eb1f9e536f8a19bc5cf06773b1febcfc8530a62dfe0"),
                      by_id("box_dry").replaces)

    def test_no_box_skips_only_the_lock(self):
        with open(NO_BOX) as source, open(self.printer.paths.config_file("box.cfg"), "w") as handle:
            handle.write(source.read())
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry"])
        applied = core.load_state(self.printer.paths)["applied"]
        self.assertIn("box_dry", applied)
        self.assertIn("box_dry_print_start", applied)
        self.assertNotIn("box_dry_lock", applied)
        self.assertFalse(self.printer.has("plus4-grease-box-lock.cfg"))
        self.assertEqual(self.printer.text("~/cfg_with_1"), stock_text("~/cfg_with_1"))
        self.assertTrue(any(line.startswith("  skipped    Box cool-down lock") for line in self.printer.lines))

    def test_without_box_drying_its_parts_are_skipped_too(self):
        changed = stock_text("printer.cfg").replace("[include KAMP_Settings.cfg]\n[include box.cfg]\n",
                                                    "[include box.cfg]\n[include KAMP_Settings.cfg]\n")
        with open(self.printer.paths.config_file("printer.cfg"), "w", newline="") as handle:
            handle.write(changed)
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry"])
        for name in ("gcode_macro.cfg", "box.cfg", "~/cfg_with_1"):
            self.assertNotIn("_GREASE_BOX", self.printer.text(name).replace("plus4-grease", ""), name)
        self.assertNotIn("box-loc", self.printer.text("box.cfg"))
        self.assertTrue(any("This works with \"Box drying" in line for line in self.printer.lines))
        self.assertFalse(self.printer.has("plus4-grease-box-dry-settings.cfg"))

    def test_a_template_sudo_cant_write_puts_everything_back(self):
        system.install(self.printer.paths, self.printer.report)  # the USB log is already there
        self.printer.sudo.fail_targets = {"cfg_with_3"}
        with self.assertRaises(GreaseError) as caught:
            core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["box-dry"])
        self.assertIn("put back", str(caught.exception))
        for name in STOCK:
            self.assertEqual(self.printer.text(name), stock_text(name), name)
        for name in ("plus4-grease-box-dry.cfg", "plus4-grease-box-lock.cfg", "plus4-grease-box-dry-settings.cfg"):
            self.assertFalse(self.printer.has(name), name)

    def test_klipper_failing_puts_the_templates_back(self):
        with self.assertRaises(GreaseError):
            core.install(self.printer.paths, FakeKlipper(ready=False), self.printer.report, options=["box-dry"])
        for name in STOCK:
            self.assertEqual(self.printer.text(name), stock_text(name), name)
        self.assertFalse(self.printer.has("plus4-grease-box-dry-settings.cfg"))

    def test_lock_is_left_out_where_klipper_lacks_a_qidi_command(self):
        for have in (QIDI_COMMANDS - {"E_BOX"}, None):
            printer = Printer()
            try:
                core.install(printer.paths, FakeKlipper(commands=have), printer.report, options=["box-dry"])
                applied = core.load_state(printer.paths)["applied"]
                self.assertIn("box_dry", applied)
                self.assertNotIn("box_dry_lock", applied)
                self.assertFalse(printer.has("plus4-grease-box-lock.cfg"))
                self.assertEqual(printer.text("box.cfg"), stock_text("box.cfg"))
                self.assertTrue(any("left out" in line for line in printer.lines))
            finally:
                printer.cleanup()

    def test_klipper_commands_come_from_the_gcode_object(self):
        from grease.klipper import Klipper

        class Moonraker(Klipper):
            def _get(self, path):
                # QIDI's E_LOAD has no help text, so it's in the gcode object's list but not in gcode/help.
                assert path == "/printer/objects/query?gcode=commands", path
                return {"status": {"gcode": {"commands": {"E_LOAD": {}, "e_box": {}, "M104": {"help": "x"}}}}}

        self.assertEqual(Moonraker().commands(), {"E_LOAD", "E_BOX", "M104"})

    def test_box_dry_replaces_the_real_0_9_0_file(self):
        here = os.path.dirname(os.path.abspath(__file__))
        feature = next(f for f in core.FEATURES if f.id == "box_dry")
        self.assertEqual(feature.replaces[0][0], "plus4-grease-box-dry.cfg")
        self.assertNotIn("PLUS4_BOX_DRY", feature.files[0][1].split("\n[", 1)[1])

    def test_klipper_failing_takes_the_new_file_away_too(self):
        with self.assertRaises(GreaseError):
            core.install(self.printer.paths, FakeKlipper(ready=False), self.printer.report,
                         options=["board-fan", "balanced-chamber"])
        self.assertFalse(os.path.exists(self.fan_file()))
        self.assertEqual(self.printer.text("printer.cfg"), stock_text("printer.cfg"))

    def test_someone_elses_fan_file_is_left_alone(self):
        with open(self.fan_file(), "w") as handle:
            handle.write("# mine\n")
        core.install(self.printer.paths, FakeKlipper(), self.printer.report, options=["board-fan"])
        with open(self.fan_file()) as handle:
            self.assertEqual(handle.read(), "# mine\n")
        self.assertIn("[controller_fan board_fan]", self.printer.text("printer.cfg"))

    def test_a_printer_that_already_changed_them_is_skipped(self):
        text = stock_text("printer.cfg").replace("max_power:0.4\n", "max_power:0.6\n").replace(
            "[controller_fan board_fan]\n", "#[controller_fan board_fan]\n")
        with open(self.printer.paths.config_file("printer.cfg"), "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        core.install(self.printer.paths, FakeKlipper(), self.printer.report,
                     options=["board-fan", "balanced-chamber"])
        applied = core.load_state(self.printer.paths)["applied"]
        self.assertNotIn("board_fan", applied)
        self.assertNotIn("balanced_chamber", applied)


class UsbLogTests(unittest.TestCase):
    def setUp(self):
        self.printer = Printer()

    def tearDown(self):
        self.printer.cleanup()

    def installed(self, path):
        return os.path.join(self.printer.system_root, path.lstrip("/"))

    def test_install_puts_the_rule_and_script_in_place_and_uninstall_removes_them(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        with open(self.installed(system.RULE)) as handle:
            rule = handle.read()
        self.assertIn('SUBSYSTEM=="usb"', rule)
        self.assertIn(system.SCRIPT, rule)
        self.assertNotIn("serial", rule)
        self.assertEqual(oct(os.stat(self.installed(system.SCRIPT)).st_mode & 0o777), "0o755")
        with open(self.installed(system.SCRIPT)) as handle:
            self.assertIn(os.path.join(self.printer.paths.home, "printer_data", "logs", system.LOG_NAME),
                          handle.read())
        self.assertIn(["udevadm", "control", "--reload-rules"], self.printer.sudo.calls)
        self.assertEqual(system.status(self.printer.paths), "applied")
        self.assertIn("usb_event_log", core.load_state(self.printer.paths)["applied"])
        self.printer.lines = []
        core.status(self.printer.paths, self.printer.report)
        self.assertTrue(any("applied    USB event log" in line for line in self.printer.lines))
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        self.assertFalse(os.path.exists(self.installed(system.RULE)))
        self.assertFalse(os.path.exists(os.path.dirname(self.installed(system.SCRIPT))))
        self.assertEqual(system.status(self.printer.paths), "available")
        self.assertEqual(core.load_state(self.printer.paths)["applied"], [])

    def test_only_the_usb_log_left_to_install(self):
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        os.unlink(self.installed(system.RULE))
        os.unlink(self.installed(system.SCRIPT))
        klipper = FakeKlipper()
        core.install(self.printer.paths, klipper, self.printer.report)
        self.assertEqual(system.status(self.printer.paths), "applied")
        self.assertEqual(klipper.restarts, 0)
        self.assertEqual(sorted(core.load_state(self.printer.paths)["applied"]), ALL_IDS)

    def test_someone_elses_file_is_left_alone(self):
        os.makedirs(os.path.dirname(self.installed(system.RULE)))
        with open(self.installed(system.RULE), "w") as handle:
            handle.write("# mine\n")
        core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        with open(self.installed(system.RULE)) as handle:
            self.assertEqual(handle.read(), "# mine\n")
        self.assertNotIn("usb_event_log", core.load_state(self.printer.paths)["applied"])
        core.uninstall(self.printer.paths, FakeKlipper(), self.printer.report)
        with open(self.installed(system.RULE)) as handle:
            self.assertEqual(handle.read(), "# mine\n")

    def test_sudo_failing_changes_nothing(self):
        self.printer.sudo.fail = {"install"}
        system.RUNNER = self.printer.sudo
        with self.assertRaises(GreaseError):
            core.install(self.printer.paths, FakeKlipper(), self.printer.report)
        for name in STOCK:
            self.assertEqual(self.printer.text(name), stock_text(name), name)
        self.assertEqual(core.load_state(self.printer.paths).get("applied", []), [])

    def test_script_writes_a_line_without_serial_numbers(self):
        script = os.path.join(self.printer.root, "usb-event")
        with open(script, "w") as handle:
            handle.write(system.script_text(self.printer.paths))
        subprocess.run(["sh", script, "add", "2-1.2.1.2", "1d50/614e/100", "Klipper", "QIDI_BOX_V1"], check=True)
        subprocess.run(["sh", script, "remove", "2-1.2.1.2", "1d50/614e/100", "", ""], check=True)
        with open(system.log_path(self.printer.paths)) as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z \d+\.\d{3} add 2-1\.2\.1\.2 "
                                   r"1d50/614e/100 Klipper QIDI_BOX_V1$")
        self.assertTrue(lines[1].endswith(" remove 2-1.2.1.2 1d50/614e/100 -"))


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
                for version in ("V1.7.1", "V1.8.0", "V2.2.0", None):
                    with self.assertRaises(GreaseError):
                        core.check_printer(printer.paths, version)
                core.check_printer(printer.paths, "V1.7.1", any_firmware=True)
                core.check_printer(printer.paths, "V2.1.1")
        finally:
            printer.cleanup()

    def test_accepts_1_8_1_and_1_8_2(self):
        printer = Printer()
        try:
            with mock.patch("os.geteuid", return_value=1000):
                for version in ("V1.8.1", "V1.8.2", "v1.8.1", "1.8.2"):
                    core.check_printer(printer.paths, version)
        finally:
            printer.cleanup()

    def test_notes_untested_firmware(self):
        self.assertIsNone(core.firmware_note("V2.1.1"))
        self.assertIsNone(core.firmware_note("V1.7.1"))
        self.assertIn("tested on V2.1.1", core.firmware_note("V1.8.1"))
        self.assertIn("V1.8.2 should work", core.firmware_note("1.8.2"))

    def test_reads_qidis_version_file(self):
        text = "[version]\nmcu             = V0.12.0\nui              = V211\nsoc             = V2.1.1"
        self.assertEqual(core.parse_soc_version(text), "V2.1.1")
        self.assertEqual(core.parse_soc_version("soc = v1.8.1\n"), "V1.8.1")
        self.assertEqual(core.parse_soc_version("mcu = V0.12.0\n"), None)


class OlderStockTests(unittest.TestCase):
    """QIDI didn't publish 1.8.1 or 1.8.2. Its published 1.7.1 configs came before them, and every edit has to
    find the same stock text there as in V2.1.1. Those configs don't include the Box templates, so the Box
    lock (box.cfg and ~/cfg_with_N) is only checked against V2.1.1's."""

    FILES = ("printer.cfg", "gcode_macro.cfg")

    def features(self):
        return [f for f in FEATURES if all(e.file in self.FILES for e in f.edits)]

    def texts(self):
        texts = {}
        for name in self.FILES:
            with open(os.path.join(HERE, "..", "stock", "plus4-1.7.1", name), "r", encoding="utf-8",
                      newline="") as handle:
                texts[name] = handle.read()
        return texts

    def test_every_change_is_available_on_stock_1_7_1(self):
        texts = self.texts()
        self.assertEqual([f.id for f in FEATURES if f not in self.features()], ["box_dry_lock"])
        for feature in self.features():
            self.assertEqual(core.feature_status(texts, feature), "available", feature.id)

    def test_every_change_applies_and_reverts_on_stock_1_7_1(self):
        original = self.texts()
        for feature in self.features():
            texts = dict(original)
            core.apply_feature(texts, feature)
            self.assertEqual(core.feature_status(texts, feature), "applied", feature.id)
            core.revert_feature(texts, feature)
            for name in original:
                self.assertEqual(texts[name], original[name], feature.id)


if __name__ == "__main__":
    unittest.main()
