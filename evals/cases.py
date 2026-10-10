"""Labeled diffs for the eval.

tier "easy": solvable by the regex heuristics (used by the offline CI gate).
tier "hard": needs real code understanding (used by the live LLM eval).
tier "team": only the team guidelines make it wrong (shows the value of RAG).
Labels are judgement calls: review and adjust them for your own taste.
"""


def _diff(path: str, lines: list[str]) -> str:
    body = "\n".join("+" + line for line in lines)
    return (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n{body}\n")


TEST = _diff("tests/test_sample.py", [
    "from app.sample import handler",
    "",
    "def test_handler_returns_input():",
    '    assert handler("x") == "x"',
])


def _case(cid: str, tier: str, expected: list[str], path: str, lines: list[str],
          with_tests: bool = True) -> dict:
    diff = _diff(path, lines) + (TEST if with_tests else "")
    return {"id": cid, "tier": tier, "expected": expected, "diff": diff}


CASES: list[dict] = [
    # ---------------- easy: regex-solvable ----------------
    _case("easy-hardcoded-secret", "easy", ["security"], "app/config.py",
          ['API_KEY = "sk-live-9f8e7d6c5b4a"']),
    _case("easy-eval", "easy", ["security"], "app/run.py",
          ["def run(request):", '    return eval(request.args["expr"])']),
    _case("easy-shell-true", "easy", ["security"], "app/sh.py",
          ["import subprocess", "", "def run(cmd):", "    subprocess.run(cmd, shell=True)"]),
    _case("easy-mutable-default", "easy", ["bug"], "app/items.py",
          ["def add_item(item, bucket=[]):", "    bucket.append(item)", "    return bucket"]),
    _case("easy-none-compare", "easy", ["bug"], "app/check.py",
          ["def check(value):", "    if value == None:", "        return 0", "    return value"]),
    _case("easy-missing-tests", "easy", ["tests"], "app/service.py",
          ["def compute(x):", "    return x * 2"], with_tests=False),
    _case("easy-long-line", "easy", ["style"], "app/msg.py",
          ['MESSAGE = "' + "x" * 130 + '"']),
    _case("easy-clean-compute", "easy", [], "app/ok.py",
          ["def compute(x):", "    return x * 2"]),
    _case("easy-clean-clamp", "easy", [], "app/util.py",
          ["def clamp(v, lo, hi):", "    return max(lo, min(v, hi))"]),
    _case("easy-clean-subprocess-list", "easy", [], "app/git.py",
          ["import subprocess", "", "def status():",
           '    return subprocess.run(["git", "status"], check=True, capture_output=True)']),
    _case("easy-clean-env-secret", "easy", [], "app/settings.py",
          ["import os", "", 'API_KEY = os.environ["API_KEY"]']),
    _case("easy-clean-with-open", "easy", [], "app/words.py",
          ["def read_words(path):", "    with open(path) as f:", "        return f.read().split()"]),
    _case("easy-clean-is-none", "easy", [], "app/check2.py",
          ["def check(value):", "    if value is None:", "        return 0", "    return value"]),

    # ---------------- hard: security ----------------
    _case("hard-path-traversal", "hard", ["security"], "app/files.py",
          ["import os", "", 'UPLOAD_DIR = "/srv/uploads"', "", "def download(request):",
           '    filename = request.args["file"]',
           "    path = os.path.join(UPLOAD_DIR, filename)",
           "    with open(path) as f:", "        return f.read()"]),
    _case("hard-pickle", "hard", ["security"], "app/session.py",
          ["import pickle", "", "def load_session(request):", "    return pickle.loads(request.body)"]),
    _case("hard-md5-password", "hard", ["security"], "app/auth.py",
          ["import hashlib", "", "def hash_password(password):",
           "    return hashlib.md5(password.encode()).hexdigest()"]),
    _case("hard-open-redirect", "hard", ["security"], "app/login.py",
          ["from flask import redirect, request", "", "def after_login():",
           '    return redirect(request.args["next"])']),
    _case("hard-jwt-no-verify", "hard", ["security"], "app/claims.py",
          ["import jwt", "", "def read_claims(token):",
           '    return jwt.decode(token, options={"verify_signature": False})']),
    _case("hard-yaml-load", "hard", ["security"], "app/cfg.py",
          ["import yaml", "", "def load_config(stream):", "    return yaml.load(stream)"]),
    _case("hard-tls-verify-off", "hard", ["security"], "app/http.py",
          ["import requests", "", "def fetch(url):", "    return requests.get(url, verify=False).text"]),
    _case("hard-missing-authz", "hard", ["security"], "app/users.py",
          ['@app.route("/users/<int:user_id>", methods=["DELETE"])',
           "def delete_user(user_id: int):", "    db.delete(User, user_id)",
           '    return {"status": "ok"}']),

    # ---------------- hard: bugs ----------------
    _case("hard-off-by-one", "hard", ["bug"], "app/sums.py",
          ["def total(items):", "    result = 0", "    for i in range(len(items) + 1):",
           "        result += items[i]", "    return result"]),
    _case("hard-missing-await", "hard", ["bug"], "app/handlers.py",
          ["async def fetch_user(uid):", "    return await db.get(uid)", "",
           "async def handler(uid):", "    user = fetch_user(uid)", "    return user.name"]),
    _case("hard-transfer-inverted", "hard", ["bug"], "app/bank.py",
          ["def transfer(src, dst, amount):", "    src.balance += amount", "    dst.balance -= amount"]),
    _case("hard-swallowed-exception", "hard", ["bug"], "app/store.py",
          ["def save(record):", "    try:", "        db.insert(record)", "    except Exception:",
           "        pass"]),
    _case("hard-resource-leak", "hard", ["bug"], "app/leak.py",
          ["def read_words(path):", "    f = open(path)", "    return f.read().split()"]),

    # ---------------- hard: tests / style ----------------
    {"id": "hard-weak-test", "tier": "hard", "expected": ["tests"],
     "diff": _diff("app/pricing.py", [
         "def apply_discount(price, rate):", "    if rate > 1:", "        raise ValueError(rate)",
         "    return price * (1 - rate)"]) + _diff("tests/test_pricing.py", [
         "from app.pricing import apply_discount", "", "def test_discount():",
         "    apply_discount(100, 0.1)"])},
    _case("hard-js-no-tests", "hard", ["tests"], "app/cart.js",
          ["export function total(items) {",
           "  return items.reduce((s, i) => s + i.price * i.qty, 0);", "}"], with_tests=False),
    _case("hard-commented-out-code", "hard", ["style"], "app/orders.py",
          ["def process(order):", "    # total = sum(i.price for i in order.items)",
           "    # if total > 100:", "    #     apply_discount(order)", "    # send_email(order)",
           "    return order.id"]),

    # ---------------- hard: clean code that LOOKS scary (precision) ----------------
    _case("hard-clean-eval-in-comment", "hard", [], "app/expr.py",
          ["import ast", "", "def evaluate(expr):", "    # never use eval() here; parse with ast instead",
           "    return ast.literal_eval(expr)"]),
    _case("hard-clean-parametrized-sql", "hard", [], "app/db_users.py",
          ["def get_user(cur, user_id):",
           '    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))',
           "    return cur.fetchone()"]),

    # ---------------- team: only the team guidelines make these wrong ----------------
    _case("team-raw-request-json", "team", ["bug"], "app/orders.py",
          ['@app.post("/orders")', "def create_order():", "    data = request.get_json()",
           '    return create(data["item"], data["qty"])']),
    _case("team-leak-exception", "team", ["bug"], "app/api.py",
          ["def handle(payload):", "    try:", "        return process(payload)",
           "    except ValueError as e:", '        return {"error": str(e)}, 400']),
    _case("team-internal-raw-requests", "team", ["security"], "app/billing.py",
          ["import requests", "", "def invoice(invoice_id):",
           '    return requests.get("http://billing.internal/api/invoices/" + invoice_id, timeout=5).json()']),
    _case("team-logger", "team", ["style"], "app/jobs.py",
          ["import logging", "", "logger = logging.getLogger(__name__)", "",
           "def run():", '    logger.info("started")']),
]