# clipboard-claim-audit

Version 0.1.0. Offline static audit of documented pasteboard delivery capabilities against Python source. Source is parsed as AST and never executed. No runtime dependencies.

Install and run:

```sh
python3 -m pip install .
clipboard-claim-audit ./project --json
python3 -m clipboard_claim_audit ./project --verbose
python3 -m unittest discover
```

The positional argument is a readable project directory. `--ignore GLOB` is repeatable and matches root-relative paths. `--fail-on HIGH` is the default; `--fail-on MEDIUM` also fails for test-only evidence. `--json` emits structured results; `--verbose` lists evidence paths in human output. `--version` prints the version. Exits: 0 for PASS, 2 for findings reaching the threshold, 1 for usage or read errors. Findings below the threshold remain visible.

Root README.md and Markdown files beneath any docs path component supply claims. Fenced blocks are excluded; inline code counts. Matching lowercases text, expands contracted negation, replaces hyphens with spaces, collapses whitespace within paragraphs, and uses word boundaries. Negative spans are removed first. Only the exact predefined phrase templates in the package constants count. A bare noun, tool name, or dependency list is insufficient. Adjacent promises about voice, SMS, email, push, network protocols, or memory and file duplication are outside scope.

Production evidence is a provider-resolved call from pyperclip, the similarly named pasteboard package, or win32clipboard. Import aliases and direct function imports are resolved per module. Tkinter method names also count when that module imports tkinter. Bare imports, strings, comments, docstrings, memory duplication and file duplication do not count. Positive promises lacking production evidence produce HIGH findings, reduced to MEDIUM when evidence exists only in tests. Negative promises conflicting with production evidence produce HIGH findings. Each family produces at most one finding. Absent claims always pass; absent source fails a positive promise and passes a negative promise.

## Limitations

This is a syntactic approximation, not runtime verification. Only the predefined exact phrase templates count; arbitrary paraphrases are not detected. Provider aliases are tracked per module without control-flow or rebinding analysis. Tkinter method detection requires an import in the same module but does not prove the receiver is a Tk instance. Qt pasteboard access and shell pasteboard helpers are not detected. Invalid source syntax supplies no evidence.

Production scanning excludes tests directories, test-prefixed and test-suffixed modules, fixtures, docs, examples, and symlinked files or directories. Test modules are scanned separately to identify MEDIUM findings; fixtures, docs and examples never supply evidence. Environment files are never opened. Glob exclusions apply to documents and source. Unreadable inputs are usage errors.
