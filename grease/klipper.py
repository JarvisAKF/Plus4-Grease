"""Talks to Klipper through Moonraker on the printer. Python 3.7."""
import json
import time
import urllib.request

from .core import GreaseError

MOONRAKER = "http://127.0.0.1:7125"


class Klipper(object):
    def __init__(self, url=MOONRAKER, sleep=time.sleep, clock=time.monotonic, timeout=240.0):
        self.url = url
        self.sleep = sleep
        self.clock = clock
        self.timeout = timeout

    def _get(self, path):
        with urllib.request.urlopen(self.url + path, timeout=10) as reply:
            return json.load(reply)["result"]

    def _post(self, path):
        request = urllib.request.Request(self.url + path, data=b"", method="POST")
        with urllib.request.urlopen(request, timeout=20) as reply:
            reply.read()

    def state(self):
        try:
            return self._get("/printer/info").get("state", "unknown")
        except Exception:  # noqa: BLE001 - Moonraker or Klipper not answering yet
            return "unknown"

    def require_idle(self):
        try:
            job = self._get("/printer/objects/query?print_stats=state")["status"]["print_stats"]["state"]
        except Exception:  # noqa: BLE001
            raise GreaseError("Can't reach Klipper through Moonraker; is the printer finished starting up?")
        if job in ("printing", "paused"):
            raise GreaseError("The printer is {}. Run this again when it's idle.".format(job))

    def restart_and_wait(self):
        """RESTART reloads the config. Returns True once Klipper is ready again."""
        try:
            self._post("/printer/restart")
        except Exception:  # noqa: BLE001 - the restart drops the connection sometimes
            pass
        self.sleep(3)
        deadline = self.clock() + self.timeout
        while self.clock() < deadline:
            state = self.state()
            if state == "ready":
                return True
            if state in ("error", "shutdown"):
                return False
            self.sleep(2)
        return False
