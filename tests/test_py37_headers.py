"""Klipper reads section headers, include lines among them, with configparser.RawConfigParser.SECTCRE
(QIDI's configfile.py). On the printer's Python 3.7 that pattern is r"\\[(?P<header>[^]]+)\\]": a name
ends at its first ']'. Newer Pythons take everything up to the last ']', so a test run on them wouldn't
notice. 0.13.0's '[s]' and '[k]' include patterns were cut that way on the owner's printer: the settings
were never loaded, and QIDI's rewrite of box.cfg broke the lock's include. Every header Plus4 Grease
writes must read the same under 3.7's rule."""
import glob
import os
import re
import unittest

from grease import edits, edits_v160

HERE = os.path.dirname(os.path.abspath(__file__))
PY37 = re.compile(r"\[(?P<header>[^]]+)\]")
WHOLE = re.compile(r"\[(?P<header>.+)\]")


def headers(text):
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if line.startswith("["):
            yield line


class HeaderTests(unittest.TestCase):
    def texts(self):
        for path in sorted(glob.glob(os.path.join(HERE, "..", "grease", "*.cfg"))):
            with open(path, encoding="utf-8") as handle:
                yield os.path.basename(path), handle.read()
        for module in (edits, edits_v160):
            for feature in module.FEATURES:
                for edit in feature.edits:
                    for text in (edit.replace,):
                        yield feature.id, text
                for name, text in feature.files or ():
                    yield name, text

    def test_every_header_reads_the_same_on_python_3_7(self):
        checked = 0
        for name, text in self.texts():
            for line in headers(text):
                whole, cut = WHOLE.match(line), PY37.match(line)
                self.assertIsNotNone(whole, (name, line))
                self.assertEqual(cut.group("header"), whole.group("header"), (name, line))
                checked += 1
        self.assertGreater(checked, 20)

    def test_the_settings_include_finds_the_settings_file(self):
        line = [h for h in headers(edits.BOX_DRY_CFG) if "settings" in h or "setting?" in h]
        self.assertEqual(line, ["[include plus4-grease-box-dry-setting?.cfg]"])
        pattern = PY37.match(line[0]).group("header")[len("include "):]
        self.assertTrue(glob.fnmatch.fnmatch(edits.BOX_SETTINGS_FILE, pattern))
        self.assertTrue(glob.has_magic(pattern))


if __name__ == "__main__":
    unittest.main()
