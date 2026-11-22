"""Command line: python3 -m grease install|uninstall|status|fluidd. Python 3.7."""
import argparse
import os
import sys

from . import VERSION, fluidd
from .core import (GreaseError, Paths, check_identity, check_printer, install, read_soc_version, status,
                   uninstall)
from .klipper import Klipper


def main(argv=None):
    parser = argparse.ArgumentParser(prog="plus4-grease", description="Plus4 Grease for the QIDI Plus 4.")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("install", help="apply the changes that fit this printer")
    run.add_argument("--dry-run", action="store_true", help="show what would change; change nothing")
    run.add_argument("--replace-own-speeds", action="store_true",
                     help="also set the Z tilt and bed mesh speeds where you've set them yourself; "
                          "uninstall puts yours back")
    run.add_argument("--board-fan", action="store_true",
                     help="also replace QIDI's board fan with one driven by the X/Y driver and mainboard chip "
                          "temperatures")
    run.add_argument("--balanced-chamber", action="store_true",
                     help="also make the chamber heater follow an average of the toolhead chip and the chamber "
                          "thermistor (max_power 0.6, max_temp 80, no 45-65 C target range or bed assist)")
    run.add_argument("--box-dry", action="store_true",
                     help="also add Box drying with a timer and humidity control (PLUS4_BOX_DRY), used by the "
                          "new Fluidd's Box card")
    run.add_argument("--any-firmware", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("uninstall", help="put QIDI's stock text back")
    sub.add_parser("status", help="show what's applied")
    web = sub.add_parser("fluidd", help="a current Fluidd on its own port, beside QIDI's (which stays on port 80)")
    web.add_argument("action", choices=("install", "remove", "status"))
    web.add_argument("--bundle", help="the {} file (looked for next to install.sh, in your home folder and in "
                                      "~/Downloads if not given)".format(fluidd.BUNDLE_NAME))
    web.add_argument("--port", type=int, default=fluidd.PORT, help="port for the new Fluidd (default 81)")
    web.add_argument("--dry-run", action="store_true", help="show what would change; change nothing")
    web.add_argument("--any-firmware", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    def report(line):
        print(line)
        sys.stdout.flush()

    paths = Paths()
    try:
        report("Plus4 Grease {}".format(VERSION))
        if args.command == "status":
            result = status(paths, report)
            fluidd.report_status(paths, report)
            return result
        if args.command == "fluidd" and args.action == "status":
            fluidd.report_status(paths, report)
            return 0
        check_identity(paths)
        report("Reading the firmware version (sudo asks for the mks password)...")
        check_printer(paths, read_soc_version(), any_firmware=getattr(args, "any_firmware", False))
        if args.command == "fluidd":
            if args.action == "remove":
                return fluidd.uninstall(paths, report)
            here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            bundle = args.bundle or fluidd.find_bundle(here, paths.home)
            return fluidd.install(paths, bundle, report, port=args.port, dry_run=args.dry_run)
        if args.command == "install":
            options = [name for name, chosen in (("board-fan", args.board_fan),
                                                 ("balanced-chamber", args.balanced_chamber),
                                                 ("box-dry", args.box_dry)) if chosen]
            return install(paths, Klipper(), report, dry_run=args.dry_run, replace_own=args.replace_own_speeds,
                           options=options)
        result = uninstall(paths, Klipper(), report)
        if fluidd.status(paths) == "applied":
            report("Plus4 Grease's Fluidd on port {} is still there; install.sh fluidd remove takes it out."
                   .format(fluidd.load_state(paths).get("port", fluidd.PORT)))
        return result
    except GreaseError as error:
        report("Stopped: {}".format(error))
        return 1
    except KeyboardInterrupt:
        report("Stopped.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
