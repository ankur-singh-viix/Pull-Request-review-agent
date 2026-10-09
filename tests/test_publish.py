import os

os.environ["USE_FAKE_LLM"] = "1"

import httpx
import pytest

from app import github_client
from app.graph import run_review
from app.nodes import split_findings
from app.state import Finding

DIFF = """diff --git a/app/x.py b/app/x.py
--- a/app/x.py
+++ b/app/x.py
@@ -1,2 +1,3 @@
 import os
+result = eval(user_input)
 x = 1
"""


def test_split_inline_vs_general():
    on_diff = Finding(category="security", severity="high", file="app/x.py", line=2, message="a")
    off_diff = Finding(category="bug", severity="low", file="app/x.py", line=99, message="b")
    no_line = Finding(category="tests", severity="medium", file="app/x.py", message="c")
    inline, general = split_findings(DIFF, [on_diff, off_diff, no_line])
    assert inline == [on_diff]
    assert general == [off_diff, no_line]


def test_dry_run_builds_inline_comments(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    out = run_review(diff=DIFF)
    c = out["inline_comments"][0]
    assert (c["path"], c["line"], c["side"]) == ("app/x.py", 2, "RIGHT")
    assert out["posted"] is False


def test_posts_review_with_inline(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    calls = {}
    monkeypatch.setattr(github_client, "get_head_sha", lambda r, n: "abc123")
    monkeypatch.setattr(github_client, "post_review",
                        lambda r, n, sha, body, comments: calls.update(sha=sha, comments=comments))
    out = run_review(repo="o/r", pr_number=1, diff=DIFF)
    assert out["posted"] and calls["sha"] == "abc123" and len(calls["comments"]) == 1


def test_falls_back_to_plain_comment_on_422(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setattr(github_client, "get_head_sha", lambda r, n: "abc123")

    def boom(*a, **k):
        raise httpx.HTTPStatusError("422", request=httpx.Request("POST", "http://x"),
                                    response=httpx.Response(422))

    posted = {}
    monkeypatch.setattr(github_client, "post_review", boom)
    monkeypatch.setattr(github_client, "post_comment", lambda r, n, body: posted.update(body=body))
    out = run_review(repo="o/r", pr_number=1, diff=DIFF)
    assert out["posted"] and "AI Review" in posted["body"]


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")