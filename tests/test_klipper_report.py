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
        self.assertIn("Klipper used up to 30% of a CPU core", out)
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

    def test_low_memory_and_a_dry_queue(self):
        out = Log().stats(20, buffer=0.05, mem=30000).add(
            "Transition to shutdown state: MCU 'U_1' shutdown: Timer too close").run()
        self.assertIn("only 29 MB of memory was free", out)
        self.assertIn("fell to 0.05 s", out)

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
