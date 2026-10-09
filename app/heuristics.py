"""Offline reviewer used as a deterministic baseline and for tests."""
import re
from collections.abc import Iterator

from app.state import Finding


def added_lines(diff: str) -> Iterator[tuple[str, int, str]]:
    file, line = "", 0
    for raw in diff.splitlines():
        if raw.startswith("+++ b/"):
            file = raw[6:]
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            line = int(m.group(1)) - 1 if m else 0
        elif raw.startswith(("---", "diff ", "index ", "+++")):
            continue
        elif raw.startswith("+"):
            line += 1
            yield file, line, raw[1:]
        elif not raw.startswith("-"):
            line += 1


SECURITY = [
    (r"\beval\(|\bexec\(", "Use of eval/exec on dynamic input", "high", 0.9),
    (r"shell\s*=\s*True", "subprocess with shell=True enables command injection", "high", 0.9),
    (r"(password|secret|api_key|token)\s*=\s*['\"][^'\"]+['\"]", "Hardcoded secret", "high", 0.85),
    (r"(SELECT|INSERT|UPDATE|DELETE).*(\+|%s|\{).*", "Possible SQL injection via string building", "high", 0.6),
]
BUGS = [
    (r"except\s*:", "Bare except swallows all errors", "medium", 0.45),
    (r"==\s*None|!=\s*None", "Compare to None with `is`", "low", 0.8),
    (r"def \w+\(.*=\s*(\[\]|\{\})", "Mutable default argument", "medium", 0.9),
]
STYLE = [
    (r"\bprint\(", "Use logging instead of print", "low", 0.4),
]


def _scan(diff: str, rules: list, category: str) -> list[Finding]:
    out = []
    for file, line, text in added_lines(diff):
        for pattern, msg, sev, conf in rules:
            if re.search(pattern, text, re.IGNORECASE if category == "security" else 0):
                out.append(Finding(category=category, severity=sev, file=file, line=line,
                                   message=msg, confidence=conf))
    return out


def review_security(diff: str) -> list[Finding]:
    return _scan(diff, SECURITY, "security")


def review_bugs(diff: str) -> list[Finding]:
    return _scan(diff, BUGS, "bug")


def review_style(diff: str) -> list[Finding]:
    out = _scan(diff, STYLE, "style")
    for file, line, text in added_lines(diff):
        if len(text) > 120:
            out.append(Finding(category="style", severity="low", file=file, line=line,
                               message="Line longer than 120 characters", confidence=0.8))
    return out


def review_tests(diff: str) -> list[Finding]:
    files = [f for f, _, _ in added_lines(diff)]
    src = sorted({f for f in files if f.endswith(".py") and "test" not in f})
    has_tests = any("test" in f for f in files)
    if src and not has_tests:
        return [Finding(category="tests", severity="medium", file=src[0], line=None,
                        message="Source changed but no tests were added or updated",
                        confidence=0.75)]
    return []
