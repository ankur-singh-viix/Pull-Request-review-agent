import os
from collections.abc import Callable

from langchain_core.prompts import ChatPromptTemplate

from app import github_client
from app.llm import get_llm, use_fake
from app.state import Finding, Findings, ReviewState, Verdict

CONF_THRESHOLD = 0.6
MAX_VERIFY = 2
MAX_DIFF_CHARS = 30_000
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}

FOCUS = {
    "security": "security vulnerabilities (injection, secrets, unsafe deserialization, authz)",
    "bug": "logic bugs, unhandled errors, race conditions, wrong edge-case behaviour",
    "style": "readability, naming, dead code, and maintainability problems",
    "tests": "missing or inadequate tests for the changed behaviour",
}


def fetch(state: ReviewState) -> dict:
    if state.get("diff"):
        return {}
    return {"diff": github_client.get_diff(state["repo"], state["pr_number"])}


def router(state: ReviewState) -> dict:
    types: set[str] = set()
    for line in state["diff"].splitlines():
        if not line.startswith("+++ b/"):
            continue
        path = line[6:]
        if "test" in path:
            types.add("tests")
        elif path.endswith((".js", ".ts", ".tsx", ".jsx", ".css", ".html")):
            types.add("frontend")
        elif path.endswith((".yml", ".yaml", ".toml", ".json", "Dockerfile")):
            types.add("config")
        else:
            types.add("backend")
    return {"change_types": sorted(types)}


def _llm_review(category: str, state: ReviewState) -> list[Finding]:
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a meticulous senior code reviewer. Review ONLY for {focus}. "
            "Report only real issues in ADDED lines. Use the file path and new-file line number. "
            "Set confidence honestly (0-1). Return an empty list if the code is fine. "
            "Change types in this PR: {types}.")),
        ("human", "Category: {category}\n\nDiff:\n{diff}"),
    ])
    chain = prompt | get_llm().with_structured_output(Findings)
    result = chain.invoke({"focus": FOCUS[category], "category": category,
                           "types": ", ".join(state.get("change_types", [])),
                           "diff": state["diff"][:MAX_DIFF_CHARS]})
    out = Findings.model_validate(result).findings
    for f in out:
        f.category = category
    return out


def make_reviewer(category: str, heuristic: Callable[[str], list[Finding]]):
    def node(state: ReviewState) -> dict:
        if use_fake():
            return {"findings": heuristic(state["diff"])}
        return {"findings": _llm_review(category, state)}
    return node


def aggregate(state: ReviewState) -> dict:
    best: dict[tuple, Finding] = {}
    for f in state.get("findings", []):
        key = (f.file, f.line, f.category)
        if key not in best or f.confidence > best[key].confidence:
            best[key] = f
    final = sorted((f for f in best.values() if f.confidence >= CONF_THRESHOLD),
                   key=lambda f: (SEV_ORDER.get(f.severity, 3), f.file, f.line or 0))
    pending = [f for f in best.values() if f.confidence < CONF_THRESHOLD]
    return {"final_findings": final, "pending": pending}


def verify(state: ReviewState) -> dict:
    """Second look at low-confidence findings; confirmed ones are promoted."""
    rescored: list[Finding] = []
    for f in state.get("pending", []):
        if use_fake():
            conf = 0.8 if f.severity in ("high", "medium") else 0.0
        else:
            prompt = ChatPromptTemplate.from_messages([
                ("system", (
                    "Decide whether this code-review finding is a real issue in the diff. "
                    "Be skeptical.")),
                ("human", "Finding: {finding}\n\nDiff:\n{diff}"),
            ])
            v = (prompt | get_llm().with_structured_output(Verdict)).invoke(
                {"finding": f.model_dump_json(), "diff": state["diff"][:MAX_DIFF_CHARS]})
            v = Verdict.model_validate(v)
            conf = max(f.confidence, v.confidence) if v.valid else 0.0
        rescored.append(f.model_copy(update={"confidence": conf}))
    return {"findings": rescored, "verify_attempts": state.get("verify_attempts", 0) + 1}


def after_aggregate(state: ReviewState) -> str:
    if state.get("pending") and state.get("verify_attempts", 0) < MAX_VERIFY:
        return "verify"
    return "publish"


def format_comment(findings: list[Finding]) -> str:
    if not findings:
        return "### 🤖 AI Review\nNo issues found. Nice work!"
    icon = {"high": "🔴", "medium": "🟠", "low": "🟡"}
    lines = [f"### 🤖 AI Review: {len(findings)} finding(s)\n"]
    for f in findings:
        loc = f"`{f.file}:{f.line}`" if f.line else f"`{f.file}`"
        lines.append(f"- {icon.get(f.severity, '⚪')} **{f.category}** {loc}: {f.message}")
    return "\n".join(lines)


def publish(state: ReviewState) -> dict:
    comment = format_comment(state.get("final_findings", []))
    dry = os.getenv("DRY_RUN", "1") == "1" or not state.get("repo")
    if dry:
        return {"comment": comment, "posted": False}
    github_client.post_comment(state["repo"], state["pr_number"], comment)
    return {"comment": comment, "posted": True}
