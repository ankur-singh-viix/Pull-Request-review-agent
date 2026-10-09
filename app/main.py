import json

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from app.github_client import verify_signature
from app.graph import run_review

app = FastAPI(title="PR Review Agent")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks,
                  x_hub_signature_256: str | None = Header(default=None),
                  x_github_event: str | None = Header(default=None)) -> dict:
    body = await request.body()
    if not verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="bad signature")
    if x_github_event != "pull_request":
        return {"ignored": x_github_event}
    payload = json.loads(body)
    if payload.get("action") not in ("opened", "synchronize", "reopened"):
        return {"ignored": payload.get("action")}
    background.add_task(run_review, payload["repository"]["full_name"], payload["number"])
    return {"queued": True}
