#!/bin/bash
# Builds the Fluidd bundle that `install.sh fluidd install` puts on the printer. Run it on a PC, not the
# printer: it needs git, Node 26 and pnpm 12, and the build takes a few minutes and about 1 GB of space.
#
#   bash tools/build_fluidd.sh            # builds v1.38.1, Plus4 Grease build 6
#   bash tools/build_fluidd.sh v1.38.1 6
#
# What it changes from upstream Fluidd:
#   * fluidd/plus4-grease.patch: a QIDI Box card on the dashboard, ported from Valve Oil's Fluidd
#     (see fluidd/README.md).
#   * Settings live in the Moonraker namespace "plus4_grease_fluidd" instead of "fluidd", so this Fluidd
#     and QIDI's never overwrite each other's layout, macros or theme.
#   * Every text file over 1 KB gets a .gz copy next to it, so nginx sends it pre-compressed
#     (gzip_static) instead of compressing it on the printer each time.
#   * plus4-grease.json records the Fluidd version and namespace for the installer.
#
# Output: dist/plus4-grease-fluidd-<tag>-<build>.zip and its SHA-256. The zip is byte-for-byte reproducible for
# the same build output (fixed file times and order).
set -eu
TAG=${1:-v1.38.1}
BUILD=${2:-6}
NAMESPACE=plus4_grease_fluidd
HERE=$(cd "$(dirname "$0")/.." && pwd)
WORK=${WORK:-$(mktemp -d)/fluidd}
OUT=${OUT:-$HERE/dist}

git clone --quiet --depth 1 --branch "$TAG" https://github.com/fluidd-core/fluidd.git "$WORK"
cd "$WORK"

git apply "$HERE/fluidd/plus4-grease.patch"
grep -q "NAMESPACE: 'fluidd'," src/globals.ts || { echo "src/globals.ts changed upstream; check the namespace patch" >&2; exit 1; }
sed -i "s/NAMESPACE: 'fluidd',/NAMESPACE: '$NAMESPACE',/" src/globals.ts

# Fluidd's package.json asks pnpm to download its own Node; use the Node on PATH instead.
node -e '
const fs = require("fs"); const p = JSON.parse(fs.readFileSync("package.json"));
for (const k of ["runtime", "packageManager"]) if (p.devEngines && p.devEngines[k]) p.devEngines[k].onFail = "warn";
fs.writeFileSync("package.json", JSON.stringify(p, null, 2) + "\n");'
pnpm install --no-frozen-lockfile
pnpm run build

mkdir -p "$OUT"
python3 - "$WORK/dist" "$OUT/plus4-grease-fluidd-$TAG-$BUILD.zip" "$TAG" "$NAMESPACE" "$BUILD" <<'EOF'
import gzip, json, os, sys, zipfile
dist, out, tag, namespace, build = sys.argv[1:6]
TEXT = (".js", ".mjs", ".css", ".svg", ".html", ".json", ".webmanifest", ".ttf", ".txt", ".map", ".woff")
with open(os.path.join(dist, "plus4-grease.json"), "w") as handle:
    json.dump({"fluidd": tag, "build": int(build), "namespace": namespace}, handle)
for folder, _, names in os.walk(dist):
    for name in names:
        path = os.path.join(folder, name)
        if name.endswith(TEXT) and os.path.getsize(path) > 1024:
            with open(path, "rb") as raw, open(path + ".gz", "wb") as packed:
                with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=packed, mtime=0) as z:
                    z.write(raw.read())
files = sorted(os.path.relpath(os.path.join(f, n), dist) for f, _, ns in os.walk(dist) for n in ns)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
    for rel in files:
        info = zipfile.ZipInfo("fluidd/" + rel.replace(os.sep, "/"), (2020, 1, 1, 0, 0, 0))
        info.external_attr = 0o644 << 16
        info.compress_type = zipfile.ZIP_STORED if rel.endswith(".gz") else zipfile.ZIP_DEFLATED
        with open(os.path.join(dist, rel), "rb") as handle:
            bundle.writestr(info, handle.read())
print("{} files".format(len(files)))
EOF
sha256sum "$OUT/plus4-grease-fluidd-$TAG-$BUILD.zip"
