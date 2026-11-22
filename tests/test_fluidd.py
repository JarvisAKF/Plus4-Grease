"""Tests for Plus4 Grease's side-by-side Fluidd, run on a computer: python3 -m unittest discover -s tests -v

Install and remove run against a scratch root with a fake sudo, a fake nginx and a fake web server, so
nothing touches the real /etc. If nginx is installed on the computer, the site file is also checked
with the real `nginx -t`.
"""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from grease import fluidd, system
from grease.core import GreaseError, Paths


def no_real_commands(command, **kwargs):
    raise AssertionError("a test tried to run a real command: {}".format(command))


system.ROOT = tempfile.mkdtemp(prefix="plus4-grease-no-root-")
system.RUNNER = no_real_commands


def make_bundle(path, namespace=fluidd.NAMESPACE, extra=()):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fluidd/index.html", '<script type="module" src="./assets/index-AbC_1.js"></script>')
        archive.writestr("fluidd/assets/index-AbC_1.js", "console.log(1)")
        archive.writestr("fluidd/assets/index-AbC_1.js.gz", b"\x1f\x8b")
        archive.writestr("fluidd/plus4-grease.json", json.dumps({"fluidd": "v1.38.1", "namespace": namespace}))
        for name, text in extra:
            archive.writestr(name, text)
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class FakeSudo(object):
    """sudo inside a scratch root. nginx -t answers from a list; each answer is (ok, output)."""

    def __init__(self, root, nginx_answers=None, reload_ok=True):
        self.root, self.calls = root, []
        self.nginx_answers = list(nginx_answers or [])
        self.reload_ok = reload_ok

    def where(self, path):
        return os.path.join(self.root, path.lstrip("/"))

    def __call__(self, command, **kwargs):
        assert command[0] == "sudo", command
        args = command[1:]
        self.calls.append(args)
        ok, output = True, ""
        if args[0] == "install":
            target = self.where(args[-1])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(args[-2], target)
        elif args[0] == "ln":
            target = self.where(args[-1])
            if os.path.lexists(target):
                os.unlink(target)
            os.symlink(self.where(args[-2]), target)
        elif args[0] == "rm":
            if os.path.lexists(self.where(args[-1])):
                os.unlink(self.where(args[-1]))
        elif args[:2] == ["nginx", "-t"]:
            ok, output = self.nginx_answers.pop(0) if self.nginx_answers else (True, "test is successful")
        elif args[:2] == ["systemctl", "reload"] or args[:3] == ["nginx", "-s", "reload"]:
            ok = self.reload_ok
        else:
            raise AssertionError("unexpected sudo command {}".format(args))
        return subprocess.CompletedProcess(command, 0 if ok else 1, stdout=output)


class FakeHttp(object):
    """The new site and Moonraker. The site answers only while the enabled site file exists."""

    def __init__(self, root, serves=True, gz=True, db=None):
        self.root, self.serves, self.gz = root, serves, gz
        self.db = {"fluidd": {"uiSettings": {"theme": 1}, "layout": {"a": 1}}} if db is None else db
        self.posts = []

    def site_up(self):
        return self.serves and os.path.lexists(os.path.join(self.root, fluidd.ENABLED.lstrip("/")))

    def get(self, url, headers=None, timeout=5):
        if url.startswith(fluidd.MOONRAKER + "/server/database/item"):
            namespace = url.split("namespace=")[1]
            if namespace not in self.db:
                return 404, {}, b"{}"
            return 200, {}, json.dumps({"result": {"value": self.db[namespace]}}).encode()
        if not self.site_up():
            return 0, {}, b""
        path = url.split(":81", 1)[1] if ":81" in url else url
        if path == "/plus4-grease.json":
            return 200, {}, json.dumps({"namespace": fluidd.NAMESPACE}).encode()
        if path == "/server/info":
            return 200, {}, b'{"result": {"klippy_state": "ready"}}'
        if path == "/index.html":
            return 200, {}, b'<script type="module" crossorigin src="./assets/index-AbC_1.js"></script>'
        if path.startswith("/assets/"):
            return 200, ({"content-encoding": "gzip"} if self.gz else {}), b""
        return 404, {}, b""

    def post_json(self, url, data, timeout=10):
        self.posts.append(data)
        self.db.setdefault(data["namespace"], {})[data["key"]] = data["value"]
        return 200


class Printer(object):
    def __init__(self, sudo=None, **http):
        self.dir = tempfile.mkdtemp(prefix="plus4-grease-fluidd-test-")
        self.root = os.path.join(self.dir, "root")
        os.makedirs(os.path.join(self.root, "etc", "nginx", "sites-enabled"))
        os.makedirs(os.path.join(self.root, "etc", "nginx", "sites-available"))
        self.paths = Paths(home=os.path.join(self.dir, "home"))
        os.makedirs(self.paths.home)
        self.bundle = os.path.join(self.dir, fluidd.BUNDLE_NAME)
        self.sha = make_bundle(self.bundle)
        self.sudo = sudo or FakeSudo(self.root)
        self.sudo.root = self.root
        self.http = FakeHttp(self.root, **http)
        self.lines = []

    def report(self, line):
        self.lines.append(line)

    def install(self, port=fluidd.PORT, busy=False, **kwargs):
        options = dict(port=port, runner=self.sudo, root=self.root, http=self.http, probe=lambda p: busy,
                       sleep=lambda s: None, expected_sha=self.sha)
        options.update(kwargs)
        return fluidd.install(self.paths, self.bundle, self.report, **options)

    def remove(self):
        return fluidd.uninstall(self.paths, self.report, runner=self.sudo, root=self.root)

    def site(self):
        path = os.path.join(self.root, fluidd.SITE.lstrip("/"))
        if not os.path.exists(path):
            return None
        with open(path) as handle:
            return handle.read()

    def enabled(self):
        return os.path.lexists(os.path.join(self.root, fluidd.ENABLED.lstrip("/")))

    def folder(self):
        return fluidd.folder(self.paths)

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class SiteTextTests(unittest.TestCase):
    def test_site_serves_the_folder_on_its_port_and_passes_moonraker_and_cameras_on(self):
        text = fluidd.site_text("/home/mks/plus4-grease-fluidd", 81)
        self.assertTrue(text.startswith(fluidd.MARKER))
        for line in ("listen 81;", "root /home/mks/plus4-grease-fluidd;", "gzip_static on;", "access_log off;",
                     "proxy_pass http://127.0.0.1:7125/websocket;", "proxy_pass http://127.0.0.1:7125$request_uri;",
                     "proxy_pass http://127.0.0.1:80;", "try_files $uri $uri/ /index.html;"):
            self.assertIn(line, text)
        self.assertNotIn("upstream", text)  # QIDI's site may already name upstreams; names are global
        self.assertNotIn("listen 80", text)

    def test_without_gzip_static_it_compresses_as_it_sends(self):
        text = fluidd.site_text("/x", 81, precompressed=False)
        self.assertNotIn("gzip_static", text)
        self.assertIn("gzip on;", text)

    @unittest.skipUnless(shutil.which("nginx") and os.path.exists("/etc/nginx/mime.types"), "nginx not installed")
    def test_real_nginx_accepts_both_versions(self):
        scratch = tempfile.mkdtemp()
        try:
            for precompressed in (True, False):
                with open(os.path.join(scratch, "site"), "w") as handle:
                    handle.write(fluidd.site_text(scratch, 28182, precompressed))
                with open(os.path.join(scratch, "nginx.conf"), "w") as handle:
                    handle.write("pid {0}/pid; error_log {0}/error.log; events {{}} http {{ include "
                                 "/etc/nginx/mime.types; include {0}/site; }}\n".format(scratch))
                done = subprocess.run(["nginx", "-t", "-c", os.path.join(scratch, "nginx.conf")],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
                self.assertEqual(done.returncode, 0, done.stdout)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.printer = None

    def tearDown(self):
        if self.printer:
            self.printer.cleanup()

    def make(self, **kwargs):
        self.printer = Printer(**kwargs)
        return self.printer

    def test_status_before_install_is_available(self):
        p = self.make()
        self.assertEqual(fluidd.status(p.paths, p.root), "available")

    def test_install_unpacks_adds_the_site_reloads_and_copies_settings_once(self):
        p = self.make()
        self.assertEqual(p.install(), 0)
        self.assertEqual(fluidd.status(p.paths, p.root), "applied")
        self.assertIn("root {};".format(p.folder()), p.site())
        self.assertTrue(p.enabled())
        self.assertTrue(os.path.isfile(os.path.join(p.folder(), "index.html")))
        self.assertTrue(os.path.isfile(os.path.join(p.folder(), "assets", "index-AbC_1.js.gz")))
        self.assertIn(["systemctl", "reload", "nginx"], p.sudo.calls)
        self.assertEqual(p.http.db[fluidd.NAMESPACE], p.http.db["fluidd"])
        self.assertEqual(fluidd.load_state(p.paths)["port"], 81)
        self.assertTrue(fluidd.load_state(p.paths)["precompressed"])
        self.assertTrue(p.lines[-1].startswith("Done."))

    def test_installing_again_says_so_and_changes_nothing(self):
        p = self.make()
        p.install()
        calls = len(p.sudo.calls)
        self.assertEqual(p.install(), 0)
        self.assertEqual(p.lines[-1], "Already installed.")
        self.assertEqual(len(p.sudo.calls), calls)

    def test_reinstall_keeps_this_fluidds_own_settings(self):
        p = self.make()
        p.http.db[fluidd.NAMESPACE] = {"layout": {"mine": 1}}
        p.install()
        self.assertEqual(p.http.db[fluidd.NAMESPACE], {"layout": {"mine": 1}})
        self.assertEqual(p.http.posts, [])

    def test_dry_run_changes_nothing(self):
        p = self.make()
        self.assertEqual(p.install(dry_run=True), 0)
        self.assertIsNone(p.site())
        self.assertFalse(os.path.exists(p.folder()))
        self.assertEqual(p.sudo.calls, [])

    def test_wrong_bundle_stops_before_anything(self):
        p = self.make()
        with self.assertRaises(GreaseError):
            p.install(expected_sha="0" * 64)
        self.assertIsNone(p.site())
        self.assertFalse(os.path.exists(p.folder()))

    def test_missing_bundle_says_where_to_put_it(self):
        p = self.make()
        with self.assertRaises(GreaseError) as caught:
            fluidd.install(p.paths, None, p.report, runner=p.sudo, root=p.root, http=p.http)
        self.assertIn(fluidd.BUNDLE_NAME, str(caught.exception))

    def test_busy_port_stops_before_anything(self):
        p = self.make()
        with self.assertRaises(GreaseError) as caught:
            p.install(busy=True)
        self.assertIn("--port", str(caught.exception))
        self.assertIsNone(p.site())

    def test_someone_elses_site_file_is_left_alone(self):
        p = self.make()
        path = os.path.join(p.root, fluidd.SITE.lstrip("/"))
        with open(path, "w") as handle:
            handle.write("server { listen 81; }\n")
        with self.assertRaises(GreaseError):
            p.install()
        self.assertEqual(p.site(), "server { listen 81; }\n")
        self.assertEqual(fluidd.status(p.paths, p.root), "skipped")

    def test_nginx_without_gzip_static_gets_the_fallback_site(self):
        p = self.make(sudo=FakeSudo(None, nginx_answers=[
            (False, 'nginx: [emerg] unknown directive "gzip_static" in /etc/nginx/sites-enabled/x:9')]))
        self.assertEqual(p.install(), 0)
        self.assertNotIn("gzip_static", p.site())
        self.assertIn("gzip on;", p.site())
        self.assertFalse(fluidd.load_state(p.paths)["precompressed"])

    def test_nginx_refusing_the_site_puts_everything_back(self):
        p = self.make(sudo=FakeSudo(None, nginx_answers=[(False, "nginx: [emerg] something else")]))
        with self.assertRaises(GreaseError) as caught:
            p.install()
        self.assertIn("put back", str(caught.exception))
        self.assertIsNone(p.site())
        self.assertFalse(p.enabled())
        self.assertFalse(os.path.exists(p.folder()))
        self.assertEqual(fluidd.load_state(p.paths), {})

    def test_page_not_answering_puts_everything_back(self):
        p = self.make(serves=False)
        with self.assertRaises(GreaseError):
            p.install()
        self.assertIsNone(p.site())
        self.assertFalse(os.path.exists(p.folder()))
        self.assertGreaterEqual(p.sudo.calls.count(["systemctl", "reload", "nginx"]), 2)

    def test_failed_upgrade_keeps_the_working_install(self):
        p = self.make()
        p.install()
        before = p.site()
        marker = os.path.join(p.folder(), "from-before")
        open(marker, "w").close()
        state = fluidd.load_state(p.paths)
        state["version"] = "v1.0.0"
        fluidd.save_state(p.paths, state)
        p.http.serves = False
        with self.assertRaises(GreaseError):
            p.install()
        self.assertEqual(p.site(), before)
        self.assertTrue(p.enabled())
        self.assertTrue(os.path.exists(marker))

    def test_bundle_with_paths_outside_its_folder_is_refused(self):
        p = self.make()
        p.sha = make_bundle(p.bundle, extra=[("fluidd/../../evil", "x")])
        with self.assertRaises(GreaseError):
            p.install()
        self.assertFalse(os.path.exists(os.path.join(p.dir, "evil")))
        self.assertIsNone(p.site())

    def test_bundle_from_somewhere_else_is_refused(self):
        p = self.make()
        p.sha = make_bundle(p.bundle, namespace="fluidd")
        with self.assertRaises(GreaseError):
            p.install()
        self.assertFalse(os.path.exists(p.folder()))

    def test_remove_takes_out_the_site_and_folder_and_keeps_settings(self):
        p = self.make()
        p.install()
        self.assertEqual(p.remove(), 0)
        self.assertIsNone(p.site())
        self.assertFalse(p.enabled())
        self.assertFalse(os.path.exists(p.folder()))
        self.assertEqual(fluidd.status(p.paths, p.root), "available")
        self.assertEqual(fluidd.load_state(p.paths), {})
        self.assertIn(fluidd.NAMESPACE, p.http.db)
        self.assertTrue(p.lines[-1].startswith("Done."))

    def test_remove_when_not_installed(self):
        p = self.make()
        self.assertEqual(p.remove(), 0)
        self.assertEqual(p.lines[-1], "Plus4 Grease's Fluidd isn't installed.")
        self.assertEqual(p.sudo.calls, [])

    def test_status_line(self):
        p = self.make()
        fluidd.report_status(p.paths, p.report, p.root)
        p.install()
        fluidd.report_status(p.paths, p.report, p.root)
        self.assertTrue(p.lines[0].startswith("  available"))
        self.assertTrue(p.lines[-1].startswith("  applied"))


if __name__ == "__main__":
    unittest.main()
