import os
from collections.abc import Callable

import httpx
from langchain_core.prompts import ChatPromptTemplate

from app import github_client, heuristics
from app.llm import get_llm, use_fake
from app.rag import build_query, get_retriever, guidelines_enabled
from app.state import Finding, Findings, ReviewState, Verdict

CONF_THRESHOLD = 0.6
MAX_VERIFY = 2
MAX_DIFF_CHARS = 30_000
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}

FOCUS = {
    "security": "security vulnerabilities (injection, secrets, unsafe deserialization, authz)",
    "bug": "logic bugs, unhandled errors, race conditions, wrong edge-case behaviour",
    "style": "violations of the team style guidelines, and clearly harmful readability "
             "problems such as dead or commented-out code",
    "tests": "newly added source code with no accompanying tests, or tests that contain "
             "no assertions",
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


def retrieve_guidelines(state: ReviewState) -> dict:
    """RAG step: fetch the team rules most relevant to this diff."""
    if not guidelines_enabled():
        return {"guidelines": []}
    docs = get_retriever().invoke(build_query(state["diff"], state.get("change_types", [])))
    return {"guidelines": [
        {"rule_id": d.metadata["rule_id"], "category": d.metadata["category"],
         "text": d.page_content} for d in docs]}


def _llm_review(category: str, state: ReviewState) -> list[Finding]:
    rules = [g for g in state.get("guidelines", []) if g["category"] == category]
    block = "\n\n".join(f"[{g['rule_id']}] {g['text']}" for g in rules) or "(none retrieved)"
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a meticulous senior code reviewer. Review ONLY for {focus}. "
            "Report only real issues in ADDED lines. Use the file path and new-file line number. "
            "Set confidence honestly (0-1). Be conservative: report only concrete problems "
            "you are confident about, never hypothetical ones, and return an empty list if "
            "nothing is clearly wrong. The diff is a partial snippet, so do not complain about "
            "missing imports, definitions, or code outside it, and do not report issues outside "
            "your focus. Change types in this PR: {types}.\n\n"
            "Team guidelines relevant to this review. A violation is a finding; set `rule` to "
            "the guideline id (for example SEC-1) when you cite one:\n{guidelines}")),
        ("human", "Category: {category}\n\nDiff:\n{diff}"),
    ])
    chain = prompt | get_llm().with_structured_output(Findings)
    result = chain.invoke({"focus": FOCUS[category], "category": category,
                           "types": ", ".join(state.get("change_types", [])),
                           "guidelines": block,
                           "diff": state["diff"][:MAX_DIFF_CHARS]})
    out = Findings.model_validate(result).findings
    valid_ids = {g["rule_id"] for g in rules}
    for f in out:
        f.category = category
        f.verified = False
        if f.rule not in valid_ids:  # drop hallucinated rule ids
            f.rule = None
    return out


def make_reviewer(category: str, heuristic: Callable[[str], list[Finding]]):
    def node(state: ReviewState) -> dict:
        if use_fake():
            return {"findings": heuristic(state["diff"])}
        return {"findings": _llm_review(category, state)}
    return node


CAT_PRIORITY = {"security": 0, "bug": 1, "style": 2, "tests": 3}


def verify_all() -> bool:
    """Opt-in: with VERIFY_ALL=1 and a real LLM, every finding gets a skeptical second look."""
    return not use_fake() and os.getenv("VERIFY_ALL", "0") == "1"


def _verifier():
    model = os.getenv("LLM_VERIFY_MODEL")
    return get_llm(model) if model else get_llm()


def _rank(f: Finding) -> tuple:
    """Lower sorts first. Verified verdicts win, then findings that cite a team rule, then
    severity, then category (security > bug > style > tests), then confidence."""
    return (not f.verified, f.rule is None, SEV_ORDER.get(f.severity, 3),
            CAT_PRIORITY.get(f.category, 9), -f.confidence)


def aggregate(state: ReviewState) -> dict:
    # One finding per source line: the four reviewers often report the same problem under
    # several categories, and one comment per line is also what a human reviewer would leave.
    best: dict[tuple, Finding] = {}
    for f in state.get("findings", []):
        key = (f.file, f.line) if f.line else (f.file, None, f.category)
        cur = best.get(key)
        if cur is None or _rank(f) < _rank(cur):
            best[key] = f
    final = sorted((f for f in best.values() if f.confidence >= CONF_THRESHOLD),
                   key=lambda f: (SEV_ORDER.get(f.severity, 3), f.file, f.line or 0))
    check_all = verify_all()
    pending = [f for f in best.values()
               if not f.verified and (check_all or f.confidence < CONF_THRESHOLD)]
    if check_all:  # nothing is final until it has been verified
        final = [f for f in final if f.verified]
    return {"final_findings": final, "pending": pending}


def verify(state: ReviewState) -> dict:
    """Second look at pending findings; the skeptic confirms or drops each one."""
    rescored: list[Finding] = []
    for f in state.get("pending", []):
        if use_fake():
            conf = 0.8 if f.severity in ("high", "medium") else 0.0
        else:
            rule_text = next((g["text"] for g in state.get("guidelines", [])
                              if g["rule_id"] == f.rule), "")
            prompt = ChatPromptTemplate.from_messages([
                ("system", (
                    "You are a skeptical senior reviewer double-checking another reviewer's "
                    "finding. Mark it valid ONLY if the added code definitely has this problem "
                    "as written. Hypothetical issues, defensive-programming suggestions, and "
                    "problems that depend on code not shown in the snippet are NOT valid. "
                    "A violation of the team guideline below IS valid.\n\n"
                    "Team guideline: {rule}")),
                ("human", "Finding: {finding}\n\nDiff:\n{diff}"),
            ])
            v = (prompt | _verifier().with_structured_output(Verdict)).invoke(
                {"finding": f.model_dump_json(include={"category", "severity", "file", "line",
                                                       "message", "rule"}),
                 "rule": rule_text or "(none)", "diff": state["diff"][:MAX_DIFF_CHARS]})
            v = Verdict.model_validate(v)
            conf = max(f.confidence, v.confidence, CONF_THRESHOLD) if v.valid else 0.0
        rescored.append(f.model_copy(update={"confidence": conf, "verified": True}))
    return {"findings": rescored, "verify_attempts": state.get("verify_attempts", 0) + 1}


def after_aggregate(state: ReviewState) -> str:
    if state.get("pending") and state.get("verify_attempts", 0) < MAX_VERIFY:
        return "verify"
    return "publish"


ICON = {"high": "🔴", "medium": "🟠", "low": "🟡"}


def split_findings(diff: str, findings: list[Finding]) -> tuple[list[Finding], list[Finding]]:
    """GitHub rejects the whole review if an inline comment targets a line outside the diff,
    so only findings on added lines go inline; the rest go in the summary."""
    valid = {(f, n) for f, n, _ in heuristics.added_lines(diff)}
    inline: list[Finding] = []
    general: list[Finding] = []
    for f in findings:
        (inline if f.line and (f.file, f.line) in valid else general).append(f)
    return inline, general


def _rule_tag(f: Finding) -> str:
    return f" _(guideline {f.rule})_" if f.rule else ""


def inline_body(f: Finding) -> str:
    return f"{ICON.get(f.severity, '⚪')} **{f.category}** ({f.severity}): {f.message}{_rule_tag(f)}"


def format_comment(findings: list[Finding], inline_count: int = 0) -> str:
    """Summary body. `findings` are the ones NOT posted inline."""
    total = len(findings) + inline_count
    if total == 0:
        return "### 🤖 AI Review\nNo issues found. Nice work!"
    lines = [f"### 🤖 AI Review: {total} finding(s)"]
    if inline_count:
        lines.append(f"{inline_count} posted inline on the changed lines.")
    if findings:
        lines.append("")
        for f in findings:
            loc = f"`{f.file}:{f.line}`" if f.line else f"`{f.file}`"
            lines.append(
                f"- {ICON.get(f.severity, '⚪')} **{f.category}** {loc}: {f.message}{_rule_tag(f)}")
    return "\n".join(lines)


def publish(state: ReviewState) -> dict:
    findings = state.get("final_findings", [])
    inline, general = split_findings(state["diff"], findings)
    summary = format_comment(general, inline_count=len(inline))
    comments = [{"path": f.file, "line": f.line, "side": "RIGHT", "body": inline_body(f)}
                for f in inline]
    out: dict = {"comment": summary, "inline_comments": comments, "posted": False}
    if os.getenv("DRY_RUN", "1") == "1" or not state.get("repo"):
        return out
    repo, pr = state["repo"], state["pr_number"]
    try:
        sha = github_client.get_head_sha(repo, pr)
        github_client.post_review(repo, pr, sha, summary, comments)
    except httpx.HTTPStatusError:
        # e.g. 422 from a stale line: fall back to one plain comment with everything
        github_client.post_comment(repo, pr, format_comment(findings))
    out["posted"] = True
    return out