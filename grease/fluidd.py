"""Plus4 Grease Fluidd: a current Fluidd served beside QIDI's. Python 3.7.

QIDI's Fluidd stays exactly as it is on port 80, Box panel and all. This adds upstream Fluidd (v1.38.1)
on port 81, served by the nginx that's already running, from its own folder (~/plus4-grease-fluidd) and
its own nginx site file. Its settings live in their own Moonraker namespace (plus4_grease_fluidd); the
first install copies QIDI Fluidd's settings in so the layout, macros and theme carry over. Removing it
deletes the site file and the folder. Nothing of QIDI's is changed at any point.

Lighter on the printer than QIDI's copy: every text file ships pre-compressed and nginx sends the .gz
as it is (gzip_static), so the mainboard compresses nothing when a browser loads the page; the hashed
asset files are cached by the browser for good; and this site writes no nginx access log.

The bundle is built by tools/build_fluidd.sh and checked against BUNDLE_SHA256 before anything is
unpacked.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import socket
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

from . import system
from .core import GreaseError

BUNDLE_VERSION = "v1.38.1"
BUNDLE_NAME = "plus4-grease-fluidd-{}.zip".format(BUNDLE_VERSION)
BUNDLE_SHA256 = "6e586522ac1cc1db755a05dc117effd51f44c840621b1f92805c991a90d0bc31"
PORT = 81
NAMESPACE = "plus4_grease_fluidd"
QIDI_NAMESPACE = "fluidd"
SITE = "/etc/nginx/sites-available/plus4-grease-fluidd"
ENABLED = "/etc/nginx/sites-enabled/plus4-grease-fluidd"
MOONRAKER = "http://127.0.0.1:7125"
MARKER = "# Plus4 Grease Fluidd site"
FOLDER_NAME = "plus4-grease-fluidd"
STATE_NAME = "fluidd.json"


def title(port=PORT):
    return "Fluidd {} on port {} (QIDI's Fluidd stays on port 80)".format(BUNDLE_VERSION, port)


def folder(paths):
    return os.path.join(paths.home, FOLDER_NAME)


def state_file(paths):
    return os.path.join(paths.state_dir, STATE_NAME)


def load_state(paths):
    try:
        with open(state_file(paths), "r") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def save_state(paths, state):
    os.makedirs(paths.state_dir, exist_ok=True)
    if state is None:
        if os.path.exists(state_file(paths)):
            os.unlink(state_file(paths))
        return
    with open(state_file(paths) + ".tmp", "w") as handle:
        json.dump(state, handle, indent=1, sort_keys=True)
    os.replace(state_file(paths) + ".tmp", state_file(paths))


# ------------------------------------------------------------------ nginx site
def site_text(root, port, precompressed=True, moonraker=MOONRAKER, cameras="http://127.0.0.1:80"):
    if precompressed:
        compression = "gzip_static on;"
    else:  # this nginx was built without gzip_static: compress as it sends instead
        compression = ("gzip on;\n    gzip_types text/css application/javascript application/json "
                       "image/svg+xml application/manifest+json;")
    return """{marker}: Fluidd {version} on port {port}, beside QIDI's Fluidd on port 80.
# Written by Plus4 Grease. Remove with: bash ~/plus4-grease/install.sh fluidd remove
server {{
    listen {port};
    server_name _;
    root {root};
    index index.html;
    access_log off;
    client_max_body_size 0;
    {compression}

    location / {{
        try_files $uri $uri/ /index.html;
    }}
    # The page and its service worker are checked on each visit; the hashed assets never change.
    location = /index.html {{
        add_header Cache-Control "no-cache";
    }}
    location = /sw.js {{
        add_header Cache-Control "no-cache";
    }}
    location /assets/ {{
        add_header Cache-Control "public, max-age=31536000, immutable";
    }}

    # Moonraker
    location /websocket {{
        proxy_pass {moonraker}/websocket;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }}
    location ~ ^/(printer|api|access|machine|server)/ {{
        proxy_pass {moonraker}$request_uri;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Scheme $scheme;
    }}

    # Cameras: passed to QIDI's own site on port 80, which knows where the camera streamer is.
    location ~ ^/webcam[0-9]*/ {{
        proxy_pass {cameras};
        proxy_buffering off;
        postpone_output 0;
        proxy_ignore_headers X-Accel-Buffering;
    }}
}}
""".format(marker=MARKER, version=BUNDLE_VERSION, port=port, root=root, compression=compression,
           moonraker=moonraker, cameras=cameras)


def _where(root, path):
    return os.path.join(root or system.ROOT, path.lstrip("/"))


def status(paths, root=None):
    """'applied' when the site file is Plus4 Grease's, 'available' when there's none, 'skipped' when a
    file of someone else's is in its place."""
    try:
        with open(_where(root, SITE), "r", encoding="utf-8") as handle:
            return "applied" if handle.read().startswith(MARKER) else "skipped"
    except FileNotFoundError:
        return "available"
    except OSError:
        return "skipped"


# ------------------------------------------------------------------ talking to things
class Http(object):
    """GET and POST with urllib. Tests swap in a fake."""

    def get(self, url, headers=None, timeout=5):
        """(status, lower-case headers, body bytes); status 0 when nothing answers."""
        request = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                return reply.status, {k.lower(): v for k, v in reply.headers.items()}, reply.read()
        except urllib.error.HTTPError as error:
            return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read()
        except (OSError, ValueError):
            return 0, {}, b""

    def post_json(self, url, data, timeout=10):
        request = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                reply.read()
                return reply.status
        except urllib.error.HTTPError as error:
            return error.code
        except (OSError, ValueError):
            return 0


def listening(port, host="127.0.0.1"):
    """True when something accepts connections on the port."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def lan_address():
    """The printer's address on the network, for the 'open this' line. Sends nothing."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# ------------------------------------------------------------------ steps
def find_bundle(here, home):
    for place in (here, home, os.path.join(home, "Downloads")):
        candidate = os.path.join(place, BUNDLE_NAME)
        if os.path.isfile(candidate):
            return candidate
    return None


def unpack(bundle, target):
    """Unpacks the zip's fluidd/ folder into target and checks it's the Plus4 Grease build."""
    with zipfile.ZipFile(bundle) as archive:
        for member in archive.infolist():
            name = member.filename
            if not name.startswith("fluidd/") or name.startswith("/") or ".." in name.split("/"):
                raise GreaseError("The bundle has an unexpected file in it ({}); not using it.".format(name))
        os.makedirs(target)
        for member in archive.infolist():
            rel = member.filename[len("fluidd/"):]
            if not rel or member.is_dir():
                continue
            out = os.path.join(target, *rel.split("/"))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with archive.open(member) as source, open(out, "wb") as sink:
                shutil.copyfileobj(source, sink)
            os.chmod(out, 0o644)
    for dirpath, dirnames, _ in os.walk(target):
        for name in dirnames:
            os.chmod(os.path.join(dirpath, name), 0o755)
    os.chmod(target, 0o755)
    try:
        with open(os.path.join(target, "plus4-grease.json")) as handle:
            info = json.load(handle)
    except (OSError, ValueError):
        info = {}
    if info.get("namespace") != NAMESPACE or not os.path.isfile(os.path.join(target, "index.html")):
        raise GreaseError("The bundle isn't a Plus4 Grease Fluidd build.")
    return info


def write_site(paths, text, runner):
    os.makedirs(paths.state_dir, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=paths.state_dir)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        ok, output = system._sudo(runner, "install", "-D", "-m", "0644", "-o", "root", "-g", "root", temp, SITE)
    finally:
        os.unlink(temp)
    if not ok:
        raise OSError("couldn't write {}: {}".format(SITE, output))
    ok, output = system._sudo(runner, "ln", "-sfn", SITE, ENABLED)
    if not ok:
        raise OSError("couldn't enable {}: {}".format(SITE, output))


def remove_site(runner):
    results = [system._sudo(runner, "rm", "-f", path) for path in (ENABLED, SITE)]
    return all(ok for ok, _ in results)


def nginx_test(runner):
    return system._sudo(runner, "nginx", "-t")


def nginx_reload(runner):
    ok, output = system._sudo(runner, "systemctl", "reload", "nginx")
    if not ok:
        ok, output = system._sudo(runner, "nginx", "-s", "reload")
    return ok, output


def last_lines(text, count=4):
    return " / ".join(line.strip() for line in text.strip().splitlines()[-count:])


def wait_until_served(http, port, sleep=time.sleep, tries=10):
    """True once the new site answers with this bundle's marker file and reaches Moonraker."""
    base = "http://127.0.0.1:{}".format(port)
    for attempt in range(tries):
        code, _, body = http.get(base + "/plus4-grease.json")
        served = False
        if code == 200:
            try:
                served = json.loads(body.decode("utf-8")).get("namespace") == NAMESPACE
            except ValueError:
                served = False
        if served:
            code, _, body = http.get(base + "/server/info")
            if code == 200 and b"klippy_state" in body:
                return True
        if attempt + 1 < tries:
            sleep(0.5)
    return False


def precompressed_sent(http, port):
    """Whether nginx sends the main script as the stored .gz."""
    base = "http://127.0.0.1:{}".format(port)
    _, _, page = http.get(base + "/index.html")
    found = re.search(rb'src="(?:\./|/)?(assets/index-[A-Za-z0-9_-]+\.js)"', page)
    if not found:
        return False
    _, headers, _ = http.get(base + "/" + found.group(1).decode("ascii"), headers={"Accept-Encoding": "gzip"})
    return headers.get("content-encoding") == "gzip"


def copy_settings(http, report):
    """Copies QIDI Fluidd's settings into this Fluidd's namespace, once: if it already has settings
    (a reinstall), they're kept."""
    url = MOONRAKER + "/server/database/item?namespace={}"
    code, _, body = http.get(url.format(NAMESPACE))
    if code == 200:
        try:
            if json.loads(body.decode("utf-8")).get("result", {}).get("value"):
                report("             Kept this Fluidd's own settings from before.")
                return
        except ValueError:
            pass
    code, _, body = http.get(url.format(QIDI_NAMESPACE))
    if code != 200:
        report("             QIDI Fluidd's settings couldn't be read, so this one starts with Fluidd's "
               "defaults.")
        return
    try:
        values = json.loads(body.decode("utf-8")).get("result", {}).get("value") or {}
    except ValueError:
        values = {}
    copied = [key for key in sorted(values)
              if http.post_json(MOONRAKER + "/server/database/item",
                                {"namespace": NAMESPACE, "key": key, "value": values[key]}) == 200]
    if copied:
        report("             Copied QIDI Fluidd's settings ({}); QIDI's stay as they are.".format(
            ", ".join(copied)))
    else:
        report("             No settings copied, so this one starts with Fluidd's defaults.")


# ------------------------------------------------------------------ actions
def install(paths, bundle, report, port=PORT, dry_run=False, runner=None, root=None, http=None,
            probe=listening, sleep=time.sleep, expected_sha=None):
    http = http or Http()
    current = status(paths, root)
    state = load_state(paths)
    report("  {:9}  {}".format(current, title(port)))
    if current == "skipped":
        raise GreaseError("{} is someone else's file, so Plus4 Grease leaves it alone.".format(SITE))
    if not os.path.isdir(_where(root, os.path.dirname(ENABLED))):
        raise GreaseError("No nginx sites folder at {}.".format(os.path.dirname(ENABLED)))
    if not bundle:
        raise GreaseError("No {} found next to install.sh, in your home folder or in ~/Downloads. Copy it "
                          "to the printer first.".format(BUNDLE_NAME))
    if sha256(bundle) != (expected_sha or BUNDLE_SHA256):
        raise GreaseError("{} isn't the file this version of Plus4 Grease expects (its SHA-256 doesn't "
                          "match). Download it again.".format(bundle))
    if (current == "applied" and state.get("version") == BUNDLE_VERSION and state.get("port") == port
            and os.path.isdir(folder(paths))):
        report("Already installed.")
        return 0
    if (current != "applied" or state.get("port") != port) and probe(port):
        raise GreaseError("Something already answers on port {}. Pick another with --port.".format(port))
    if dry_run:
        report("             Would unpack {} to {}, add the nginx site {} and reload nginx.".format(
            os.path.basename(bundle), folder(paths), SITE))
        report("Dry run: nothing was changed.")
        return 0

    target, fresh, old = folder(paths), folder(paths) + ".new", folder(paths) + ".old"
    for leftover in (fresh, old):
        shutil.rmtree(leftover, ignore_errors=True)
    report("Unpacking {}...".format(os.path.basename(bundle)))
    try:
        unpack(bundle, fresh)
    except (OSError, zipfile.BadZipFile) as error:
        shutil.rmtree(fresh, ignore_errors=True)
        raise GreaseError("The bundle couldn't be unpacked: {}.".format(error))
    except GreaseError:
        shutil.rmtree(fresh, ignore_errors=True)
        raise
    had_folder = os.path.isdir(target)
    if had_folder:
        os.rename(target, old)
    os.rename(fresh, target)
    old_site = None
    if current == "applied":
        with open(_where(root, SITE), "r", encoding="utf-8") as handle:
            old_site = handle.read()

    def put_back(reason):
        if old_site is not None:
            try:
                write_site(paths, old_site, runner)
            except OSError:
                pass
        else:
            remove_site(runner)
        if nginx_test(runner)[0]:
            nginx_reload(runner)
        shutil.rmtree(target, ignore_errors=True)
        if had_folder:
            os.rename(old, target)
        raise GreaseError(reason + " Everything was put back as it was; QIDI's Fluidd on port 80 wasn't "
                                   "touched.")

    precompressed = True
    try:
        write_site(paths, site_text(target, port, precompressed), runner)
        ok, output = nginx_test(runner)
        if not ok and "gzip_static" in output:
            precompressed = False
            write_site(paths, site_text(target, port, precompressed), runner)
            ok, output = nginx_test(runner)
    except OSError as error:
        put_back("The nginx site couldn't be written: {}.".format(error))
    if not ok:
        put_back("nginx didn't accept the new site ({}).".format(last_lines(output)))
    ok, output = nginx_reload(runner)
    if not ok:
        put_back("nginx didn't reload ({}).".format(last_lines(output)))
    report("Checking the new page...")
    if not wait_until_served(http, port, sleep):
        put_back("The new page didn't answer on port {} or didn't reach Moonraker.".format(port))
    shutil.rmtree(old, ignore_errors=True)
    sent_gz = precompressed and precompressed_sent(http, port)
    report("             Pre-compressed files: {}.".format(
        "sent as stored" if sent_gz else "no, nginx compresses as it sends"))
    copy_settings(http, report)
    save_state(paths, {"version": BUNDLE_VERSION, "port": port, "folder": target,
                       "precompressed": sent_gz,
                       "installed_at": datetime.datetime.now().isoformat(timespec="seconds")})
    address = lan_address() or "<printer address>"
    report("Done. Open http://{}:{}/ for the new Fluidd. QIDI's is still at http://{}/ .".format(
        address, port, address))
    return 0


def uninstall(paths, report, runner=None, root=None):
    current = status(paths, root)
    target = folder(paths)
    port = load_state(paths).get("port", PORT)
    if current == "skipped":
        report("  left alone  {} isn't Plus4 Grease's file.".format(SITE))
    elif current == "applied":
        if not remove_site(runner):
            raise GreaseError("The nginx site {} couldn't be removed.".format(SITE))
        ok, output = nginx_test(runner)
        if ok:
            ok, output = nginx_reload(runner)
        if not ok:
            report("             nginx reported: {}".format(last_lines(output)))
    if os.path.isdir(target):
        shutil.rmtree(target)
    if current != "applied" and not load_state(paths):
        report("Plus4 Grease's Fluidd isn't installed.")
        return 0
    save_state(paths, None)
    report("  removed    {}".format(title(port)))
    report("             Its settings stay in Moonraker's database ({}), so installing it again picks "
           "them up.".format(NAMESPACE))
    report("Done. QIDI's Fluidd on port 80 is unchanged.")
    return 0


def report_status(paths, report, root=None):
    current = status(paths, root)
    state = load_state(paths)
    note = ""
    if current == "applied" and state.get("version") and state.get("version") != BUNDLE_VERSION:
        note = " (installed: {}; install again to update)".format(state["version"])
    elif current == "available":
        note = "\n             Off unless you ask: install.sh fluidd install adds it."
    report("  {:9}  {}{}".format(current, title(state.get("port", PORT)), note))
