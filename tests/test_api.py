import hashlib
import hmac
import json
import os

os.environ["USE_FAKE_LLM"] = "1"
os.environ["GITHUB_WEBHOOK_SECRET"] = "s3cret"

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_rejects_bad_signature():
    r = client.post("/webhook", content=b"{}", headers={"X-Hub-Signature-256": "sha256=bad"})
    assert r.status_code == 401


def test_ignores_non_pr_event():
    body = b"{}"
    sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    r = client.post("/webhook", content=body,
                    headers={"X-Hub-Signature-256": sig, "X-GitHub-Event": "push"})
    assert r.json() == {"ignored": "push"}


def test_ignores_irrelevant_action():
    body = json.dumps({"action": "closed"}).encode()
    sig = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    r = client.post("/webhook", content=body,
                    headers={"X-Hub-Signature-256": sig, "X-GitHub-Event": "pull_request"})
    assert r.json() == {"ignored": "closed"}
