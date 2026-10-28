"""Tests 1–27 plus one independently named test for every exact phrase."""
import contextlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from clipboard_claim_audit import POSITIVE, NEGATIVE, audit, claims, evidence, main, normalize, pattern

ROOT = Path(__file__).resolve().parents[1]
GOOD = 'from pyperclip import copy\ncopy("result")\n'


class AuditTests(unittest.TestCase):
    def project(self, doc='copy to clipboard', source='', filename='app.py', fail_on='HIGH', extra=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text(doc)
            if source is not None:
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source)
            for name, text in (extra or {}).items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            return audit(root, fail_on=fail_on)

    def good(self, source, doc='copy to clipboard'):
        self.assertEqual(self.project(doc, source)['findings'], [])

    def bad(self, source):
        result = self.project(source=source)
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual([f['severity'] for f in result['findings']], ['HIGH'])

    def test_01_plain(self): self.good(GOOD)
    def test_02_module_alias(self): self.good('import pyperclip as pc\npc.copy(1)', 'copies to clipboard')
    def test_03_function_alias(self): self.good('from pyperclip import paste as p\np()', 'paste from clipboard')
    def test_04_paste(self): self.good('import pyperclip\npyperclip.paste()', 'paste from clipboard')
    def test_05_package(self): self.good('import clipboard\nclipboard.copy(1)')
    def test_06_tk_append(self): self.good('import tkinter\nroot.clipboard_append(1)')
    def test_07_tk_get(self): self.good('import tkinter as tk\nroot.clipboard_get()')
    def test_08_win32(self): self.good('import win32clipboard\nwin32clipboard.SetClipboardData(1)')
    def test_09_import(self): self.bad('import pyperclip')
    def test_10_strings(self): self.bad('"clipboard"\nx="pyperclip.copy(1)"')
    def test_11_memory(self): self.bad('import copy\nx=[]\nx.copy()\ncopy.copy(x)\ncopy.deepcopy(x)')
    def test_12_files(self): self.bad('import shutil\nshutil.copy(a,b)\nshutil.copytree(a,b)\nshutil.copyfile(a,b)')
    def test_13_tk_missing(self): self.bad('root.clipboard_append(1)\nroot.clipboard_get()')
    def test_14_negative(self):
        result = self.project('no clipboard support', GOOD)
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual([(f['rule'], f['severity']) for f in result['findings']], [('documented-no-clipboard-claim-false', 'HIGH')])
    def test_15_no_claim(self): self.good(GOOD, 'ordinary project')
    def test_16_noun(self): self.good('import pyperclip', 'the clipboard chapter explains delivery')
    def test_17_voice(self): self.good(GOOD, 'voice input')
    def test_18_sms(self): self.good(GOOD, 'sms notifications')
    def test_19_no_source(self):
        self.assertEqual(self.project(source=None)['verdict'], 'FAIL')
        self.assertEqual(self.project('no clipboard support', None)['verdict'], 'PASS')
    def test_20_tests_only(self):
        for filename in ['tests/helper.py', 'test_driver.py', 'driver_test.py']:
            for threshold, verdict in [('HIGH', 'PASS'), ('MEDIUM', 'FAIL')]:
                result = self.project(source=GOOD, filename=filename, fail_on=threshold)
                self.assertEqual(result['verdict'], verdict)
                self.assertEqual(result['findings'][0]['severity'], 'MEDIUM')
    def test_21_fences_inline(self):
        for fence in ['```', '~~~']:
            self.good('', fence + '\ncopy to clipboard\n' + fence)
        self.assertEqual(self.project('`copy to clipboard`')['verdict'], 'FAIL')
    def test_22_negation(self): self.assertEqual(claims('does not use clipboard'), (False, True))
    def test_23_self_audit(self):
        result = audit(ROOT)
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['claims'], dict(positive=False, negative=False))
        for path in [ROOT / 'README.md'] + list(ROOT.glob('**/docs/**/*.md')):
            text = normalize(path.read_text())
            self.assertIsNone(pattern(POSITIVE + NEGATIVE).search(text))
            self.assertIsNone(re.search(r'\b(using|uses|with|via|over|supports|sends|send) clipboard claim audit\b', text))
    def invoke(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            try: code = main(args)
            except SystemExit as error: code = error.code
        return code, output.getvalue()
    def test_24_cli(self):
        good = str(ROOT / 'tests/fixtures/good')
        bad = str(ROOT / 'tests/fixtures/bad')
        self.assertEqual(self.invoke(['--version']), (0, '0.1.0\n'))
        self.assertEqual(json.loads(self.invoke([good, '--json'])[1])['verdict'], 'PASS')
        self.assertIn('app.py', self.invoke([good, '--verbose'])[1])
        self.assertEqual(self.invoke([bad])[0], 2)
        self.assertEqual(self.invoke([bad, '--ignore', 'README.md'])[0], 0)
        for args in [[], ['/nonexistent/path'], [good, '--fail-on', 'LOW'], [good, '--unknown']]:
            self.assertEqual(self.invoke(args)[0], 1)
    def test_25_env_guard(self):
        original = Path.open
        def guarded(path, *args, **kwargs):
            self.assertNotEqual(path.name, '.env')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded):
            self.assertEqual(audit(ROOT)['verdict'], 'PASS')
    def test_26_packaging(self):
        config = (ROOT / 'pyproject.toml').read_text()
        self.assertIn('setuptools>=77', config)
        self.assertIn('license = "MIT"', config)
        self.assertIn('requires-' + 'py' + 'thon = ">=3.9"', config)
        self.assertIn('recursive-include tests', (ROOT / 'MANIFEST.in').read_text())
        for path in list((ROOT / 'clipboard_claim_audit').glob('*.py')) + list((ROOT / 'tests').glob('*.py')) + [ROOT / 'README.md']:
            # Construct the forbidden command token so the test does not match itself.
            self.assertIsNone(re.search(r'\b' + 'py' + r'thon\b', path.read_text()), str(path))
    def test_27_phrase_exhaustion_registered(self):
        self.assertEqual(len(POSITIVE), 28)
        self.assertEqual(len(NEGATIVE), 8)
        self.assertEqual(len([n for n in dir(type(self)) if n.startswith('test_phrase_')]), 36)

    def test_additional_exclusions(self):
        for source in ['from PyQt5.QtWidgets import QApplication\nQApplication.clipboard().setText("x")', 'import subprocess\nsubprocess.run(["pbcopy"])', 'def clipboard_send():\n print("x")', '@app.get("/")\ndef endpoint():\n return "clipboard"', 'email.send()\nsms.send()\npush.send()']:
            self.bad(source)
        for doc in ['email notifications', 'push notifications', 'webhook websocket server-sent events GraphQL gRPC MQTT', 'copies files', 'copies results']:
            self.good('', doc)

    def test_additional_routes(self):
        for source in ['from clipboard import paste as p\np()', 'import clipboard as cb\ncb.paste()', 'from win32clipboard import GetClipboardData as g\ng()', 'import win32clipboard as wc\nwc.GetClipboardData()', 'from tkinter import Tk\nr.clipboard_get()', 'import pyperclip.extra as pc\npc.copy(1)', 'from pyperclip.extra import copy as c\nc(1)']:
            self.good(source)

    def test_scope_and_normalization(self):
        for filename in ['fixtures/app.py', 'docs/app.py', 'examples/app.py']:
            self.assertEqual(self.project(source=GOOD, filename=filename)['verdict'], 'FAIL')
        self.assertEqual(claims("DOESN'T use clipboard"), (False, True))
        self.assertEqual(claims('Copies-results\nto clipboard'), (True, False))
        self.assertEqual(claims('copy to\n\nclipboard'), (False, False))
        self.assertEqual(claims('xcopy to clipboardx'), (False, False))
        self.assertEqual(self.project('ordinary', GOOD, extra={'nested/docs/guide.md': 'no clipboard support'})['verdict'], 'FAIL')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('copy to clipboard')
            (root / 'linked.py').symlink_to(ROOT / 'tests/fixtures/good/app.py')
            self.assertEqual(audit(root)['verdict'], 'FAIL')
        self.assertFalse(evidence('from .pyperclip import copy\ncopy(1)'))


def phrase_test(phrase, negative):
    def test(self):
        self.assertEqual(claims(phrase), (not negative, negative))
        result = self.project(phrase, GOOD if negative else '')
        self.assertEqual(result['verdict'], 'FAIL')
        self.assertEqual(result['findings'][0]['severity'], 'HIGH')
        self.assertEqual(result['findings'][0]['rule'], 'documented-no-clipboard-claim-false' if negative else 'documented-clipboard-claim-false')
    test.__doc__ = 'Exact phrase coverage: ' + phrase
    return test


for index, phrase in enumerate(POSITIVE + NEGATIVE):
    setattr(AuditTests, 'test_phrase_%02d' % index, phrase_test(phrase, phrase in NEGATIVE))
