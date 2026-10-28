"""Static pasteboard documentation audit."""
import ast
import fnmatch
import json
import os
import re
import argparse
from pathlib import Path

__version__ = '0.1.0'
POSITIVE = (
    'copies results to clipboard', 'copies to the clipboard', 'copies to clipboard',
    'copy results to clipboard', 'copy to the clipboard', 'copy to clipboard',
    'copied to the clipboard', 'copied to clipboard', 'pastes from clipboard',
    'paste from clipboard', 'reads from clipboard', 'read from clipboard',
    'writes to clipboard', 'write to clipboard', 'clipboard integration',
    'clipboard functionality', 'clipboard support', 'clipboard copy',
    'clipboard paste', 'clipboard access', 'clipboard enabled', 'clipboard based',
    'supports clipboard', 'supports the clipboard', 'uses clipboard',
    'using clipboard', 'via clipboard', 'with clipboard',
)
NEGATIVE = (
    'does not copy to clipboard', 'does not use clipboard',
    'does not support clipboard', 'no clipboard integration',
    'no clipboard support', 'clipboard not supported', 'without clipboard',
    'no clipboard',
)
PROVIDERS = {'pyperclip', 'clipboard', 'tkinter', 'win32clipboard'}


def normalize(text):
    return ' '.join(text.lower().replace("n't", ' not').replace('-', ' ').split())


def pattern(phrases):
    return re.compile(r'\b(?:' + '|'.join(re.escape(p) for p in sorted(phrases, key=len, reverse=True)) + r')\b')


def claims(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not line[match.end():].strip():
                fence = None
            continue
        if match:
            fence = match[1]
            continue
        lines.append(line)
    positive = negative = False
    for paragraph in re.split(r'\n\s*\n', '\n'.join(lines)):
        paragraph = normalize(paragraph)
        negative = negative or bool(pattern(NEGATIVE).search(paragraph))
        paragraph = pattern(NEGATIVE).sub(' ', paragraph)
        positive = positive or bool(pattern(POSITIVE).search(paragraph))
    return positive, negative


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + '.' + node.attr if base else ''
    return ''


def evidence(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    aliases = {}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                provider = item.name.split('.')[0]
                if provider in PROVIDERS:
                    imported.add(provider)
                    aliases[item.asname or provider] = item.name if item.asname else provider
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            provider = node.module.split('.')[0]
            if provider in PROVIDERS:
                imported.add(provider)
                for item in node.names:
                    aliases[item.asname or item.name] = node.module + '.' + item.name
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {'clipboard_append', 'clipboard_get'} and 'tkinter' in imported:
            return True
        path = dotted(func)
        head, sep, tail = path.partition('.')
        resolved = aliases.get(head, '')
        if not resolved:
            continue
        path = resolved + (sep + tail if sep else '')
        provider = path.split('.')[0]
        method = path.rsplit('.', 1)[-1]
        if provider in {'pyperclip', 'clipboard'} and method in {'copy', 'paste'}:
            return True
        if provider == 'win32clipboard' and method in {'SetClipboardData', 'GetClipboardData'}:
            return True
    return False


def audit(root, ignore=(), fail_on='HIGH'):
    root = Path(root)
    if not root.is_dir() or not os.access(str(root), os.R_OK | os.X_OK):
        raise ValueError('Root must be a readable directory')
    positive = negative = False
    prod, tests = [], []
    errors = []
    def walk_error(error):
        errors.append(error)
    for directory, dirs, files in os.walk(str(root), followlinks=False, onerror=walk_error):
        dirs[:] = sorted(d for d in dirs if not Path(directory, d).is_symlink() and not any(fnmatch.fnmatch(Path(directory, d).relative_to(root).as_posix(), g) for g in ignore))
        for name in sorted(files):
            path = Path(directory, name)
            rel = path.relative_to(root)
            if path.is_symlink() or any(fnmatch.fnmatch(rel.as_posix(), g) for g in ignore):
                continue
            is_doc = rel.as_posix() == 'README.md' or ('docs' in rel.parts[:-1] and path.suffix == '.md')
            is_source = path.suffix == '.py' and not any(p in {'fixtures', 'docs', 'examples'} for p in rel.parts[:-1])
            if not (is_doc or is_source):
                continue
            text = path.read_text(encoding='utf-8')
            if is_doc:
                pos, neg = claims(text)
                positive |= pos
                negative |= neg
            if is_source and evidence(text):
                test = 'tests' in rel.parts[:-1] or name.startswith('test_') or name.endswith('_test.py')
                (tests if test else prod).append(rel.as_posix())
    if errors:
        raise ValueError(str(errors[0]))
    findings = []
    if positive and not prod:
        findings.append(dict(rule='documented-clipboard-claim-false', severity='MEDIUM' if tests else 'HIGH', message='Documented pasteboard capability has evidence only in tests.' if tests else 'Documented pasteboard capability lacks production evidence.'))
    if negative and prod:
        findings.append(dict(rule='documented-no-clipboard-claim-false', severity='HIGH', message='Documented absence conflicts with production pasteboard evidence.'))
    failed = any(f['severity'] == 'HIGH' or fail_on == 'MEDIUM' for f in findings)
    return dict(verdict='FAIL' if failed else 'PASS', findings=findings, claims=dict(positive=positive, negative=negative), evidence=prod, test_evidence=tests)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(__import__('sys').stderr)
        self.exit(1, self.prog + ': error: ' + message + '\n')


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--ignore', action='append', default=[])
    parser.add_argument('--fail-on', choices=['HIGH', 'MEDIUM'], default='HIGH')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)
    try:
        result = audit(args.root, args.ignore, args.fail_on)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(1, 'error: ' + str(exc) + '\n')
    if args.json:
        print(json.dumps(result))
    else:
        print(result['verdict'])
        for finding in result['findings']:
            print('{severity} {rule}: {message}'.format(**finding))
        if args.verbose:
            print('Production evidence: ' + ', '.join(result['evidence']))
            print('Test evidence: ' + ', '.join(result['test_evidence']))
    return 2 if result['verdict'] == 'FAIL' else 0
