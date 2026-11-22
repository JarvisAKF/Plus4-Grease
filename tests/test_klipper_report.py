"""Tests for tools/klipper_report.py against made-up klippy.log files in Klipper's own line formats
(klippy.py, configfile.py, mcu.py, toolhead.py, heaters.py, statistics.py of QIDI's Plus 4 Klipper)."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import klipper_report  # noqa: E402

HEADER = """Starting Klippy...
Start printer at Sat Nov 21 15:40:00 2026 (1795297200.0 1000.0)
===== Config file =====
[mcu]
serial = /dev/ttyS2
baud = 500000

[mcu U_1]
serial = /dev/ttyS0

[extruder]
step_pin = PB9
microsteps = 16

[stepper_x]
step_pin = U_1:PB4
microsteps = 32

[stepper_y]
step_pin = U_1:PC14
microsteps = 32

[stepper_z]
step_pin = U_1:PB1
microsteps = 128

[gcode_macro TEST]
gcode =
\tSET_VELOCITY_LIMIT VELOCITY=100
=======================
Loaded MCU 'mcu' 120 commands (v0.12.0 / gcc)
MCU 'mcu' config: MCU=stm32f103xe CLOCK_FREQ=72000000 SERIAL_BAUD=500000
Loaded MCU 'U_1' 130 commands (v0.12.0 / gcc)
MCU 'U_1' config: MCU=stm32f401xc CLOCK_FREQ=84000000 SERIAL_BAUD=500000
"""


class Log(object):
    """Builds Stats lines second by second."""

    def __init__(self, t=1010.0):
        self.lines = HEADER.splitlines()
        self.t = t
        self.cpu = 100.0
        self.print_time = 5.0
        self.u1_bytes = 0
        self.u1_resent = 9
        self.stall = 0

    def stats(self, seconds=1, cpu=0.3, buffer=1.5, u1_awake=0.5, u1_rate=4000, u1_resend=0, mem=640000,
              load=0.4, step=1.0, temp=219.8):
        for _ in range(seconds):
            self.t += step
            self.cpu += cpu * step
            self.print_time += step
            self.u1_bytes += int(u1_rate * step)
            self.u1_resent += u1_resend
            self.lines.append(
                "Stats {:.1f}: gcodein=0  mcu: mcu_awake=0.010 mcu_task_avg=0.000015 mcu_task_stddev=0.000010 "
                "bytes_write=5000 bytes_read=1000 bytes_retransmit=9 bytes_invalid=0 send_seq=1 receive_seq=1 "
                "retransmit_seq=2 srtt=0.001 rttvar=0.000 rto=0.025 ready_bytes=0 upcoming_bytes=0 "
                "freq=72000780 U_1: mcu_awake={:.3f} mcu_task_avg=0.000024 mcu_task_stddev=0.000020 "
                "bytes_write={} bytes_read=2000 bytes_retransmit={} bytes_invalid=0 send_seq=1 receive_seq=1 "
                "retransmit_seq=2 srtt=0.000 rttvar=0.000 rto=0.025 ready_bytes=0 upcoming_bytes=0 "
                "freq=84002515 adj=84001592 heater_bed: target=60 temp=60.1 pwm=0.300 print_time={:.3f} "
                "buffer_time={:.3f} print_stall={} extruder: target=220 temp={:.1f} pwm=0.400 sysload={:.2f} "
                "cputime={:.3f} memavail={}".format(
                    self.t, u1_awake, self.u1_bytes, self.u1_resent, self.print_time, buffer, self.stall, temp,
                    load, self.cpu, mem))
        return self

    def add(self, text):
        self.lines.extend(text.splitlines())
        return self

    def write(self, path):
        with open(path, "w") as out:
            out.write("\n".join(self.lines) + "\n")
        return path

    def run(self, *args):
        handle, path = tempfile.mkstemp(suffix=".log")
        os.close(handle)
        self.write(path)
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                klipper_report.main([path] + list(args))
        finally:
            os.unlink(path)
        return buffer.getvalue()

    def run_with_usb(self, usb_lines, *args):
        folder = tempfile.mkdtemp()
        try:
            path = self.write(os.path.join(folder, "klippy.log"))
            if usb_lines is not None:
                with open(os.path.join(folder, "plus4-grease-usb.log"), "w") as out:
                    out.write("\n".join(usb_lines) + "\n")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                klipper_report.main([path] + list(args))
            return buffer.getvalue()
        finally:
            for name in os.listdir(folder):
                os.unlink(os.path.join(folder, name))
            os.rmdir(folder)

    def scan(self):
        handle, path = tempfile.mkstemp(suffix=".log")
        os.close(handle)
        try:
            return klipper_report.scan([self.write(path)])
        finally:
            os.unlink(path)


class ReportTests(unittest.TestCase):
    def test_last_print_reads_only_its_own_stats(self):
        log = Log().add("Starting SD card print (position 0)").stats(10, u1_awake=4.0)
        log.add("Finished SD card print").stats(30, u1_awake=0.1)
        log.add("Starting SD card print (position 0)").stats(20, u1_awake=1.0).add("Finished SD card print")
        log.stats(30, u1_awake=3.0)
        out = log.run()
        self.assertIn("Board 'U_1' (stm32f401xc): busy up to 20% (fine)", out)
        self.assertIn("19 s of Stats, finished", out)

    def test_a_print_across_two_days_files(self):
        first = Log().add("Starting SD card print (position 0)").stats(10, u1_awake=0.5)
        second = Log()
        second.lines = ["=============== Log rollover at Sun Nov 22 00:00:00 2026 ==============="] + \
            HEADER.splitlines()[2:]
        second.t, second.cpu, second.print_time = first.t, first.cpu, first.print_time
        second.u1_bytes, second.u1_resent = first.u1_bytes, first.u1_resent
        second.stats(10, u1_awake=4.0).add("Finished SD card print")
        folder = tempfile.mkdtemp()
        try:
            path = os.path.join(folder, "klippy.log")
            first.write(path + ".2026-11-21")
            second.write(path)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                klipper_report.main([path, "--all"])
            out = buffer.getvalue()
        finally:
            for name in os.listdir(folder):
                os.unlink(os.path.join(folder, name))
            os.rmdir(folder)
        self.assertIn("busy up to 80% (near its limit)", out)
        self.assertIn("finished", out)

    def test_no_print_reports_the_last_stats(self):
        out = Log().stats(30).run()
        self.assertIn("No print in this log. The last 30 s of Stats instead", out)

    def test_a_clean_print(self):
        out = Log().add("Starting SD card print (position 0)").stats(60).add("Finished SD card print").run()
        self.assertIn("'U_1': stm32f401xc at 84 MHz, serial 500000 baud", out)
        self.assertIn("stepper_z at 128 microsteps", out)
        self.assertIn("'mcu': stm32f103xe at 72 MHz", out)
        self.assertIn("extruder at 16 microsteps", out)
        self.assertIn("59 s of Stats, finished", out)
        self.assertIn("Klipper used up to 30% of a CPU core at", out)
        self.assertIn("0 seconds at 80% or more", out)
        self.assertIn("The move queue never ran dry", out)
        self.assertIn("main loop never stopped", out)
        self.assertIn("Board 'U_1' (stm32f401xc): busy up to 10% (fine)", out)
        self.assertIn("8% of its serial link", out)  # 4000 bytes/s of 50000
        self.assertIn("No shutdowns in this log", out)
        self.assertNotIn("SET_VELOCITY_LIMIT VELOCITY", out)

    def test_timer_too_close_after_the_pi_stalled(self):
        log = Log().add("Starting SD card print (position 0)").stats(20).stats(1, step=3.0).stats(2)
        out = log.add("Transition to shutdown state: MCU 'U_1' shutdown: Timer too close\n"
                      "This often indicates the host computer is overloaded.").run()
        self.assertIn("MCU 'U_1' shutdown: Timer too close", out)
        self.assertIn("The Pi fell behind: Klipper's main loop stopped for about 2.0 s", out)
        self.assertIn("Klipper shut down: MCU 'U_1' shutdown: Timer too close", out)

    def test_timer_too_close_with_nothing_in_the_numbers(self):
        out = Log().stats(20).add("Transition to shutdown state: MCU 'mcu' shutdown: Timer too close").run()
        self.assertIn("Nothing in Klipper's statistics points to", out)

    def test_lost_communication_with_resends(self):
        out = Log().stats(10).stats(10, u1_resend=40).add(
            "Timeout with MCU 'U_1' (eventtime=1031.0)\n"
            "Transition to shutdown state: Lost communication with MCU 'U_1'").run()
        self.assertIn("The serial link had errors: board 'U_1' resent 400 bytes", out)

    def test_lost_communication_with_no_warning_signs(self):
        out = Log().stats(20).add("Transition to shutdown state: Lost communication with MCU 'mcu'").run()
        self.assertIn("Board 'mcu' stopped answering without link errors", out)

    def test_stepping_too_fast(self):
        out = Log().stats(20, u1_awake=4.6).add(
            "Transition to shutdown state: MCU 'U_1' shutdown: Rescheduled timer in the past").run()
        self.assertIn("Board 'U_1' was asked to step faster than it can. It drives stepper_x at 32 microsteps, "
                      "stepper_y at 32 microsteps, stepper_z at 128 microsteps.", out)
        self.assertIn("board 'U_1' was busy 92% of the time", out)

    def test_temperature_out_of_range(self):
        out = Log().stats(5, temp=305.2).add(
            "Transition to shutdown state: MCU 'mcu' shutdown: ADC out of range").run()
        self.assertIn("extruder 305.2°C (target 220)", out)

    def test_homing_and_probing_dont_count_as_a_dry_queue(self):
        out = Log().add("Starting SD card print (position 0)").stats(5, buffer=0.0).stats(20).add(
            "Finished SD card print").run()
        self.assertIn("never ran dry", out)

    def test_a_resume_is_the_same_print(self):
        log = Log().add("Starting SD card print (position 0)").stats(30).add("Starting SD card print (position 5123)")
        out = log.stats(30).add("Finished SD card print").run()
        self.assertIn("59 s of Stats, resumed 1 time after a pause, finished", out)

    def test_busy_stretches_show_what_klipper_logged(self):
        log = Log().add("Starting SD card print (position 0)").stats(20).add("bed_mesh: generated points")
        log.stats(6, cpu=0.95).stats(20).add("Finished SD card print")
        out = log.run()
        self.assertIn("6 seconds at 80% or more", out)
        self.assertIn(": 6 s, peak 95%", out)
        self.assertIn("        bed_mesh: generated points", out)

    def test_a_real_dry_queue(self):
        log = Log().add("Starting SD card print (position 0)").stats(10)
        log.stall = 3
        out = log.stats(10).add("Transition to shutdown state: MCU 'U_1' shutdown: Timer too close").run()
        self.assertIn("the move queue ran dry 3 times", out)

    def test_usb_board_losing_its_connection(self):
        log = Log()
        log.lines.append("MCU 'mcu_box1' config: MCU=stm32f401xc CLOCK_FREQ=84000000")
        out = log.stats(20).add("Transition to shutdown state: Lost communication with MCU 'mcu_box1'").run()
        self.assertIn("its USB connection dropped", out)
        self.assertIn("Nov 21 ", out)

    def box_log(self):
        log = Log()
        log.lines.append("MCU 'mcu_box1' config: MCU=stm32f401xc CLOCK_FREQ=84000000")
        # Start line: epoch 1795297200.0 at monotonic 1000.0; 20 Stats lines end at t=1030, epoch 1795297230.
        return log.stats(20).add("Transition to shutdown state: Lost communication with MCU 'mcu_box1'")

    START_LINE = "2026-11-21T00:00:00.000Z 1795290000.000 start - - Plus4 Grease USB log installed"

    def test_box_switched_off_shows_the_usb_disconnect(self):
        out = self.box_log().run_with_usb([
            self.START_LINE,
            "2026-11-21T00:01:00.000Z 1795290060.000 add 2-1.2.1.2 1d50/614e/100 Klipper QIDI_BOX_V1",
            "2026-11-21T15:40:29.400Z 1795297229.400 remove 2-1.2.1.2 1d50/614e/100 -",
        ])
        self.assertIn("Linux saw a USB disconnect just before: Klipper QIDI_BOX_V1 disconnected on USB port "
                      "2-1.2.1.2 (0.6 s before the last Stats line). The board was switched off, unplugged, "
                      "lost power, or reset", out)
        self.assertNotIn("most likely its USB connection dropped", out)
        self.assertIn("USB events: 2 in plus4-grease-usb.log, the last 5:", out)

    def test_power_flicker_on_the_box(self):
        out = self.box_log().run_with_usb([
            self.START_LINE,
            "2026-11-21T00:01:00.000Z 1795290060.000 add 2-1.2.1.2 1d50/614e/100 Klipper QIDI_BOX_V1_1.1.1",
            "2026-11-21T15:40:29.400Z 1795297229.400 remove 2-1.2.1.2 1d50/614e/100 -",
            "2026-11-21T15:40:29.450Z 1795297229.450 remove 2-1.2.1 1a40/801/100 -",
            "2026-11-21T15:40:31.000Z 1795297231.000 add 2-1.2.1 1a40/801/100 USB 2.0 Hub",
            "2026-11-21T15:40:31.400Z 1795297231.400 add 2-1.2.1.2 483/5740/200 MKS COLOR BOOT",
            "2026-11-21T15:40:33.900Z 1795297233.900 remove 2-1.2.1.2 483/5740/200 -",
            "2026-11-21T15:40:34.300Z 1795297234.300 add 2-1.2.1.2 1d50/614e/100 Klipper QIDI_BOX_V1_1.1.1",
        ])
        self.assertIn("Klipper QIDI_BOX_V1_1.1.1 was gone for 4.9 s and started again from its bootloader, so "
                      "it lost power or reset; a gap that short is a power flicker or a reset", out)
        self.assertIn("Devices that went away and came back (the last 1):", out)

    def test_box_switched_off_by_hand_for_a_while(self):
        out = self.box_log().run_with_usb([
            self.START_LINE,
            "2026-11-22T00:03:08.526Z 1795305788.526 remove 2-1.2.1.2 1d50/614e/100 -",
            "2026-11-22T00:03:38.672Z 1795305818.672 add 2-1.2.1.2 483/5740/200 MKS COLOR BOOT",
            "2026-11-22T00:03:41.184Z 1795305821.184 remove 2-1.2.1.2 483/5740/200 -",
            "2026-11-22T00:03:41.568Z 1795305821.568 add 2-1.2.1.2 1d50/614e/100 Klipper QIDI_BOX_V1_1.1.1",
        ])
        self.assertIn("Klipper QIDI_BOX_V1_1.1.1 was gone for 33.0 s and started again from its bootloader, so "
                      "it lost power or reset.", out)
        self.assertNotIn("power flicker", out)

    def test_box_stopped_answering_without_leaving_usb(self):
        out = self.box_log().run_with_usb([self.START_LINE])
        self.assertIn("Linux saw no USB device disconnect around it, so it stayed connected to the Pi", out)

    def test_without_the_usb_log(self):
        out = self.box_log().run_with_usb(None)
        self.assertIn("No USB event log yet", out)
        self.assertIn("most likely its USB connection dropped", out)

    def test_usb_log_started_after_the_shutdown_proves_nothing(self):
        late = "2026-11-22T00:00:00.000Z 1795400000.000 start - - Plus4 Grease USB log installed"
        out = self.box_log().run_with_usb([late])
        self.assertIn("most likely its USB connection dropped", out)
        self.assertNotIn("Linux saw no USB device disconnect", out)

    def test_kinds_of_start(self):
        log = Log().stats(3).add("Attempting MCU 'mcu' reset\nRestarting printer")
        log.add("Start printer at Sat Nov 21 15:50:00 2026 (1795297800.0 2000.0)").stats(3)
        log.add("box_detect: box1 removed\nRestarting printer")
        log.add("Start printer at Sat Nov 21 15:55:00 2026 (1795298100.0 3000.0)").stats(3)
        out = log.run_with_usb([
            self.START_LINE,
            "2026-11-21T15:54:55.000Z 1795298095.000 remove 2-1.2.1.2 1d50/614e/100 -"])
        self.assertIn("Klipper starts (the last 3):", out)
        self.assertIn("Klipper's service started", out)
        self.assertIn("FIRMWARE_RESTART", out)
        self.assertIn("RESTART (Klipper reloaded its config", out)
        self.assertIn("      logged before it: box_detect: box1 removed", out)
        self.assertIn("      USB 5.0 s before: a USB device (1d50/614e/100) disconnected on USB port 2-1.2.1.2", out)

    def test_box_loss_restart_and_cancelled_print(self):
        log = Log().add("Starting SD card print (position 0)").stats(5).add(
            "Exiting SD card print (position 8066)\naction:cancel\nb'Got EOF when reading from device'\n"
            "Updated new device path: /dev/serial/by-id/usb-Klipper_QIDI_BOX_V1_1.1.1_0123456789ABCDEF01234567-if00\n"
            "webhooks client 281473754271136: Disconnected\nStarting Klippy...")
        log.add("Start printer at Sat Nov 21 15:55:00 2026 (1795298100.0 3000.0)").stats(3)
        out = log.run()
        self.assertIn("A board's serial port closed under Klipper before this", out)
        self.assertIn("A print was cancelled at file position 8066 before this.", out)
        self.assertIn("usb-Klipper_QIDI_BOX_V1_1.1.1_<serial>-if00", out)
        self.assertNotIn("0123456789ABCDEF01234567", out)
        self.assertNotIn("webhooks client", out)
        self.assertIn("stopped at file position 8066 (cancelled, or paused and not resumed)", out)

    def test_shutdown_says_how_long_klipper_stayed_down(self):
        log = Log().stats(5).add("Transition to shutdown state: Lost communication with MCU 'mcu_box1'")
        log.add("Starting Klippy...\nStart printer at Sat Nov 21 18:00:00 2026 (1795305600.0 9000.0)").stats(2)
        out = log.run()
        self.assertIn("Klipper stayed shut down until it started again 2.3 h later", out)

    def test_low_memory_and_a_dry_queue(self):
        out = Log().stats(20, buffer=0.05, mem=30000).add(
            "Transition to shutdown state: MCU 'U_1' shutdown: Timer too close").run()
        self.assertIn("only 29 MB of memory was free", out)

    def test_a_new_days_file_continues_the_session(self):
        log = Log().stats(5).add("=============== Log rollover at Sun Nov 22 00:00:00 2026 ===============")
        log.add("\n".join(HEADER.splitlines()[2:])).stats(5)
        sessions = log.scan().sessions
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].stat_count, 10)

    def test_a_restart_starts_a_new_session(self):
        log = Log().stats(5).add("\n".join(HEADER.splitlines()[1:]).replace("1000.0)", "2000.0)"))
        sessions = log.stats(5).scan().sessions
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[1].boards["U_1"]["MCU"], "stm32f401xc")
        self.assertIn("stepper_x", dict(sessions[1].motors()["U_1"]))


if __name__ == "__main__":
    unittest.main()
