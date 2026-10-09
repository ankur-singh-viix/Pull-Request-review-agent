import hashlib
import hmac
import os

import httpx

API = "https://api.github.com"


def _headers(accept: str = "application/vnd.github+json") -> dict[str, str]:
    h = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token := os.getenv("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {token}"
    return h


def get_diff(repo: str, pr_number: int) -> str:
    r = httpx.get(f"{API}/repos/{repo}/pulls/{pr_number}",
                  headers=_headers("application/vnd.github.v3.diff"), timeout=30)
    r.raise_for_status()
    return r.text


def get_head_sha(repo: str, pr_number: int) -> str:
    r = httpx.get(f"{API}/repos/{repo}/pulls/{pr_number}", headers=_headers(), timeout=30)
    r.raise_for_status()
    return str(r.json()["head"]["sha"])


def post_review(repo: str, pr_number: int, commit_sha: str, body: str,
                comments: list[dict]) -> None:
    """One PR review with inline comments (Pull Request Review API)."""
    r = httpx.post(f"{API}/repos/{repo}/pulls/{pr_number}/reviews", headers=_headers(),
                   json={"commit_id": commit_sha, "body": body, "event": "COMMENT",
                         "comments": comments}, timeout=30)
    r.raise_for_status()


def post_comment(repo: str, pr_number: int, body: str) -> None:
    r = httpx.post(f"{API}/repos/{repo}/issues/{pr_number}/comments",
                   headers=_headers(), json={"body": body}, timeout=30)
    r.raise_for_status()


def verify_signature(payload: bytes, signature: str | None) -> bool:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)