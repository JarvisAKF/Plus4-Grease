#!/bin/bash
# Plus4 Grease launcher. Run it on the printer as mks:
#   bash install.sh install --dry-run   # show what would change
#   bash install.sh install             # apply it
#   bash install.sh status
#   bash install.sh uninstall
set -eu
here=$(cd "$(dirname "$0")" && pwd)
command -v python3 >/dev/null 2>&1 || { echo "python3 is missing." >&2; exit 1; }
cd "$here"
exec python3 -m grease "${@:-status}"
