"""Command line: python3 -m grease install|uninstall|status. Python 3.7."""
import argparse
import sys

from . import VERSION
from .core import (GreaseError, Paths, check_identity, check_printer, install, read_soc_version, status,
                   uninstall)
from .klipper import Klipper


def main(argv=None):
    parser = argparse.ArgumentParser(prog="plus4-grease", description="Plus4 Grease for the QIDI Plus 4.")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("install", help="apply the changes that fit this printer")
    run.add_argument("--dry-run", action="store_true", help="show what would change; change nothing")
    run.add_argument("--any-firmware", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("uninstall", help="put QIDI's stock text back")
    sub.add_parser("status", help="show what's applied")
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
            return status(paths, report)
        check_identity(paths)
        report("Reading the firmware version (sudo asks for the mks password)...")
        check_printer(paths, read_soc_version(), any_firmware=getattr(args, "any_firmware", False))
        if args.command == "install":
            return install(paths, Klipper(), report, dry_run=args.dry_run)
        return uninstall(paths, Klipper(), report)
    except GreaseError as error:
        report("Stopped: {}".format(error))
        return 1
    except KeyboardInterrupt:
        report("Stopped.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
