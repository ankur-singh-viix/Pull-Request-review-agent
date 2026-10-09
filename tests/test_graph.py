import os

os.environ["USE_FAKE_LLM"] = "1"
os.environ["DRY_RUN"] = "1"

from app.graph import run_review
from app.heuristics import added_lines

BAD = """diff --git a/app/x.py b/app/x.py
--- a/app/x.py
+++ b/app/x.py
@@ -1,2 +1,5 @@
 import os
+API_KEY = "sk-live-123456"
+result = eval(user_input)
+def f(a=[]):
+    pass
"""
CLEAN = """diff --git a/tests/test_a.py b/tests/test_a.py
--- a/tests/test_a.py
+++ b/tests/test_a.py
@@ -0,0 +1,2 @@
+def test_ok():
+    assert 1 == 1
"""


def test_line_numbers():
    rows = list(added_lines(BAD))
    assert rows[0] == ("app/x.py", 2, 'API_KEY = "sk-live-123456"')


def test_detects_security_and_bugs():
    out = run_review(diff=BAD)
    cats = {f.category for f in out["final_findings"]}
    assert {"security", "bug", "tests"} <= cats
    assert out["final_findings"][0].severity == "high"   # sorted by severity
    assert out["posted"] is False


def test_clean_diff_has_no_findings():
    assert run_review(diff=CLEAN)["final_findings"] == []


def test_verify_loop_promotes_pending():
    diff = BAD.replace("+result = eval(user_input)", "+try:\n+    pass\n+except:\n+    pass")
    out = run_review(diff=diff)
    assert any("Bare except" in f.message for f in out["final_findings"])
    assert out["verify_attempts"] >= 1


def test_router_classifies_files():
    out = run_review(diff=BAD + CLEAN)
    assert "backend" in out["change_types"] and "tests" in out["change_types"]
