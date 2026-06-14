"""PR templates covering the full spectrum of code quality issues.

Each template defines the shape of a pull request: language, change type,
intentional issues seeded into the diff, and a structured annotation list
that records per-dimension ground truth used to score reviewer agreement.

The 12 dimensions (matching backend/agent/rubric.py):
  correctness, security, performance, readability, error_handling,
  test_coverage, api_consistency, documentation, dependency_hygiene,
  breaking_changes, code_duplication, edge_cases
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DIMENSIONS = [
    "correctness",
    "security",
    "performance",
    "readability",
    "error_handling",
    "test_coverage",
    "api_consistency",
    "documentation",
    "dependency_hygiene",
    "breaking_changes",
    "code_duplication",
    "edge_cases",
]


@dataclass
class DimensionAnnotation:
    dimension: str    # one of the 12 dimension names
    expected: bool    # True = a good reviewer should flag this
    rationale: str    # one-sentence ground-truth explanation


def _ann(dimension: str, expected: bool, rationale: str) -> DimensionAnnotation:
    return DimensionAnnotation(dimension=dimension, expected=expected, rationale=rationale)


def _clean(notes: dict[str, str]) -> list[DimensionAnnotation]:
    """Build a full 12-dimension annotation list.

    Pass only the dimensions that are flagged (expected=True) plus any
    that have a special False rationale. All others default to expected=False
    with a generic 'No issue in this change' rationale.
    """
    result = []
    for dim in DIMENSIONS:
        if dim in notes:
            text = notes[dim]
            expected = not text.startswith("OK:")
            rationale = text[3:].strip() if text.startswith("OK:") else text
        else:
            expected = False
            rationale = "No issue introduced by this change."
        result.append(_ann(dim, expected, rationale))
    return result


@dataclass
class PRTemplate:
    name: str
    language: str         # python | typescript | go | java | rust
    change_type: str      # feature | bugfix | refactor | dependency | docs
    description: str
    diff_template: str
    annotations: list[DimensionAnnotation]
    severity: str = "medium"   # low | medium | high | critical

    @property
    def expected_findings(self) -> list[str]:
        """Derived list for backwards compatibility with simulation code."""
        return [a.dimension for a in self.annotations if a.expected]


# ---------------------------------------------------------------------------
# Python templates (20 total: 10 original + 10 new)
# ---------------------------------------------------------------------------

TEMPLATES: list[PRTemplate] = [

    # --- Original 10 Python templates ---

    PRTemplate(
        name="sql_injection",
        language="python",
        change_type="feature",
        severity="critical",
        description="Add user search endpoint with raw SQL",
        diff_template="""\
--- a/api/users.py
+++ b/api/users.py
@@ -10,6 +10,15 @@
+def search_users(query: str):
+    sql = f"SELECT * FROM users WHERE name = '{query}'"
+    return db.execute(sql).fetchall()
""",
        annotations=_clean({
            "security": "Raw f-string SQL interpolation allows arbitrary SQL injection.",
            "correctness": "No return type annotation; missing pagination or LIMIT clause.",
            "error_handling": "No exception handling if db.execute raises.",
            "edge_cases": "Empty string or None query is not guarded against.",
        }),
    ),

    PRTemplate(
        name="n_plus_one_query",
        language="python",
        change_type="feature",
        severity="high",
        description="Render order list with per-item DB call",
        diff_template="""\
--- a/views/orders.py
+++ b/views/orders.py
@@ -5,5 +5,10 @@
+def render_orders(order_ids):
+    orders = []
+    for oid in order_ids:
+        orders.append(Order.objects.get(id=oid))
+    return orders
""",
        annotations=_clean({
            "performance": "N+1 query pattern: one DB round-trip per order_id.",
            "error_handling": "Order.objects.get raises DoesNotExist if id is missing; not handled.",
            "edge_cases": "Empty order_ids list not guarded; could return empty list silently.",
        }),
    ),

    PRTemplate(
        name="missing_error_handling",
        language="python",
        change_type="bugfix",
        severity="medium",
        description="Parse JSON from external API without error handling",
        diff_template="""\
--- a/services/external.py
+++ b/services/external.py
@@ -3,4 +3,8 @@
+def fetch_data(url: str):
+    response = requests.get(url)
+    return response.json()["data"]
""",
        annotations=_clean({
            "error_handling": "No try/except for network errors, non-200 status, or missing 'data' key.",
            "edge_cases": "response.json() raises if body is not valid JSON.",
            "correctness": "response.raise_for_status() is not called; silent 4xx/5xx errors.",
        }),
    ),

    PRTemplate(
        name="hardcoded_secret",
        language="python",
        change_type="feature",
        severity="critical",
        description="Add payment integration with hardcoded API key",
        diff_template="""\
--- a/payments/stripe.py
+++ b/payments/stripe.py
@@ -1,3 +1,8 @@
+import stripe
+
+STRIPE_KEY = "sk_live_abc123supersecretkey"
+stripe.api_key = STRIPE_KEY
+
+def charge(amount: int):
+    return stripe.Charge.create(amount=amount, currency="usd")
""",
        annotations=_clean({
            "security": "Live Stripe key hardcoded in source — will be committed to version control.",
            "dependency_hygiene": "stripe not listed in requirements.txt.",
            "error_handling": "stripe.error.StripeError not caught.",
            "edge_cases": "Negative or zero amounts not validated before charging.",
        }),
    ),

    PRTemplate(
        name="missing_tests",
        language="python",
        change_type="feature",
        severity="medium",
        description="Add business logic with no corresponding tests",
        diff_template="""\
--- a/billing/calculator.py
+++ b/billing/calculator.py
@@ -0,0 +1,25 @@
+def calculate_discount(user_tier: str, amount: float) -> float:
+    if user_tier == "premium":
+        return amount * 0.8
+    elif user_tier == "enterprise":
+        return amount * 0.6
+    return amount
""",
        annotations=_clean({
            "test_coverage": "No tests added for the three discount branches or unknown tier.",
            "edge_cases": "Negative amount and unknown tier values not handled.",
            "documentation": "No docstring describing tier values or return semantics.",
        }),
    ),

    PRTemplate(
        name="good_refactor",
        language="python",
        change_type="refactor",
        severity="low",
        description="Extract utility function with proper docs and types",
        diff_template="""\
--- a/utils/formatting.py
+++ b/utils/formatting.py
@@ -0,0 +1,18 @@
+def format_currency(amount: float, currency: str = "USD") -> str:
+    \"\"\"Format a monetary amount with currency symbol.
+
+    Args:
+        amount: Amount in major currency units.
+        currency: ISO 4217 currency code.
+
+    Returns:
+        Formatted string e.g. '$12.34'.
+    \"\"\"
+    symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
+    symbol = symbols.get(currency, currency + " ")
+    return f"{symbol}{amount:,.2f}"
""",
        annotations=_clean({
            "OK:correctness": "Logic is correct; currency fallback is reasonable.",
            "OK:documentation": "Docstring is complete with Args and Returns.",
        }),
    ),

    PRTemplate(
        name="breaking_api_change",
        language="python",
        change_type="refactor",
        severity="high",
        description="Rename public function without deprecation shim",
        diff_template="""\
--- a/api/auth.py
+++ b/api/auth.py
@@ -5,6 +5,6 @@
-def verify_token(token: str) -> bool:
+def validate_jwt(token: str) -> bool:
     payload = jwt.decode(token, SECRET, algorithms=["HS256"])
     return payload is not None
""",
        annotations=_clean({
            "breaking_changes": "verify_token is a public API; renaming breaks existing callers silently.",
            "api_consistency": "New name validate_jwt uses a different verb_noun pattern than existing verify_* functions.",
        }),
    ),

    PRTemplate(
        name="duplicate_logic",
        language="python",
        change_type="feature",
        severity="low",
        description="Copy-paste email validation in new module",
        diff_template="""\
--- a/notifications/email.py
+++ b/notifications/email.py
@@ -0,0 +1,12 @@
+import re
+
+def is_valid_email(email: str) -> bool:
+    # Same regex already exists in users/validators.py
+    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
+    return bool(re.match(pattern, email))
+
+def send_notification(email: str, message: str) -> None:
+    if is_valid_email(email):
+        smtp_client.send(email, message)
""",
        annotations=_clean({
            "code_duplication": "is_valid_email duplicates users/validators.py — two copies will diverge.",
            "error_handling": "smtp_client.send errors are silently swallowed.",
        }),
    ),

    PRTemplate(
        name="blocking_io_in_async",
        language="python",
        change_type="feature",
        severity="high",
        description="Call blocking requests library inside async handler",
        diff_template="""\
--- a/handlers/webhook.py
+++ b/handlers/webhook.py
@@ -3,5 +3,10 @@
+async def process_webhook(payload: dict):
+    # blocking call inside async context
+    response = requests.post(CALLBACK_URL, json=payload)
+    return response.status_code
""",
        annotations=_clean({
            "performance": "requests.post blocks the event loop; use httpx.AsyncClient or aiohttp instead.",
            "error_handling": "Network errors and non-2xx responses from CALLBACK_URL are not handled.",
        }),
    ),

    PRTemplate(
        name="integer_overflow_risk",
        language="python",
        change_type="feature",
        severity="medium",
        description="Compute user score without bounds checking",
        diff_template="""\
--- a/scoring/engine.py
+++ b/scoring/engine.py
@@ -0,0 +1,10 @@
+def compute_score(events: list[dict]) -> int:
+    total = 0
+    for event in events:
+        total += event["points"] * event.get("multiplier", 1)
+    return total
""",
        annotations=_clean({
            "edge_cases": "Missing 'points' key raises KeyError; no guard for None multiplier.",
            "correctness": "No maximum score cap; multiplier could be a float producing non-int return.",
        }),
    ),

    # --- 10 new Python templates ---

    PRTemplate(
        name="mutable_default_argument",
        language="python",
        change_type="bugfix",
        severity="medium",
        description="Add cache helper with mutable default argument",
        diff_template="""\
--- a/utils/cache.py
+++ b/utils/cache.py
@@ -0,0 +1,8 @@
+def get_or_set(key: str, value, store: dict = {}):
+    if key not in store:
+        store[key] = value
+    return store[key]
""",
        annotations=_clean({
            "correctness": "Mutable default dict is shared across all calls — classic Python gotcha.",
            "edge_cases": "None value cannot be distinguished from a cache miss.",
            "documentation": "No docstring; the shared-state behavior is completely non-obvious.",
        }),
    ),

    PRTemplate(
        name="bare_except",
        language="python",
        change_type="feature",
        severity="medium",
        description="Add retry logic with bare except clause",
        diff_template="""\
--- a/utils/retry.py
+++ b/utils/retry.py
@@ -0,0 +1,10 @@
+def with_retry(fn, retries=3):
+    for attempt in range(retries):
+        try:
+            return fn()
+        except:
+            if attempt == retries - 1:
+                raise
""",
        annotations=_clean({
            "error_handling": "Bare except catches BaseException including KeyboardInterrupt and SystemExit.",
            "correctness": "On last attempt, raise re-raises the caught exception but loses the original traceback context.",
            "readability": "Function lacks type annotations and the retry logic is hard to follow.",
        }),
    ),

    PRTemplate(
        name="thread_race_condition",
        language="python",
        change_type="feature",
        severity="high",
        description="Increment shared counter without lock",
        diff_template="""\
--- a/metrics/counter.py
+++ b/metrics/counter.py
@@ -0,0 +1,10 @@
+_count = 0
+
+def increment():
+    global _count
+    _count += 1
+
+def get():
+    return _count
""",
        annotations=_clean({
            "correctness": "Read-modify-write on _count is not atomic; concurrent calls produce lost updates.",
            "performance": "Global state creates contention; should use threading.Lock or atomic integer.",
            "test_coverage": "No concurrency tests; race is invisible in single-threaded unit tests.",
        }),
    ),

    PRTemplate(
        name="regex_redos",
        language="python",
        change_type="feature",
        severity="high",
        description="Validate input with a catastrophically backtracking regex",
        diff_template="""\
--- a/api/validator.py
+++ b/api/validator.py
@@ -0,0 +1,7 @@
+import re
+
+EMAIL_RE = re.compile(r'^(a+)+$')
+
+def validate_input(s: str) -> bool:
+    return bool(EMAIL_RE.match(s))
""",
        annotations=_clean({
            "security": "Pattern (a+)+ is vulnerable to ReDoS with inputs like 'aaaaab' — exponential backtracking.",
            "performance": "Catastrophic backtracking can hang the server thread on adversarial input.",
            "correctness": "Regex does not match emails; variable name EMAIL_RE is misleading.",
        }),
    ),

    PRTemplate(
        name="unused_import",
        language="python",
        change_type="refactor",
        severity="low",
        description="Add new module with stale unused imports",
        diff_template="""\
--- a/services/billing.py
+++ b/services/billing.py
@@ -0,0 +1,10 @@
+import os
+import sys
+import json
+import datetime
+
+def get_billing_period() -> str:
+    from datetime import date
+    return str(date.today().replace(day=1))
""",
        annotations=_clean({
            "dependency_hygiene": "os, sys, json, datetime are imported at module level but never used.",
            "readability": "Local import inside function is inconsistent with module-level import style.",
        }),
    ),

    PRTemplate(
        name="open_redirect",
        language="python",
        change_type="feature",
        severity="critical",
        description="Add redirect endpoint using unvalidated user input",
        diff_template="""\
--- a/api/redirects.py
+++ b/api/redirects.py
@@ -0,0 +1,8 @@
+from flask import redirect, request
+
+@app.route('/go')
+def go():
+    url = request.args.get('url', '/')
+    return redirect(url)
""",
        annotations=_clean({
            "security": "Unvalidated redirect destination enables open redirect phishing attacks.",
            "correctness": "No allowlist check — any external URL can be redirected to.",
            "edge_cases": "None/empty url defaults to '/' but is not sanitised for javascript: URIs.",
        }),
    ),

    PRTemplate(
        name="datetime_naive",
        language="python",
        change_type="feature",
        severity="medium",
        description="Store event timestamps using naive datetime objects",
        diff_template="""\
--- a/models/event.py
+++ b/models/event.py
@@ -0,0 +1,8 @@
+from datetime import datetime
+
+class Event:
+    def __init__(self, name: str):
+        self.name = name
+        self.created_at = datetime.now()
""",
        annotations=_clean({
            "correctness": "datetime.now() returns a naive datetime (no tzinfo); will cause comparison errors with UTC-aware values.",
            "edge_cases": "DST transitions can produce duplicate or missing timestamps in local time.",
        }),
    ),

    PRTemplate(
        name="password_in_log",
        language="python",
        change_type="feature",
        severity="critical",
        description="Log user credentials during authentication",
        diff_template="""\
--- a/auth/login.py
+++ b/auth/login.py
@@ -5,5 +5,10 @@
+def login(username: str, password: str):
+    logger.debug(f"Login attempt: user={username} pass={password}")
+    user = User.query.filter_by(username=username).first()
+    if not user or not check_password_hash(user.password_hash, password):
+        return None
+    return user
""",
        annotations=_clean({
            "security": "Plaintext password logged to debug output — will appear in log files and APM traces.",
            "readability": "Logging credential fields is a code-review red flag regardless of log level.",
        }),
    ),

    PRTemplate(
        name="missing_pagination",
        language="python",
        change_type="feature",
        severity="high",
        description="Return all database rows without limit",
        diff_template="""\
--- a/api/reports.py
+++ b/api/reports.py
@@ -0,0 +1,7 @@
+def get_all_events():
+    return db.session.query(Event).all()
+
+@app.route('/events')
+def events():
+    return jsonify([e.to_dict() for e in get_all_events()])
""",
        annotations=_clean({
            "performance": "Unbounded .all() query loads entire table into memory; will OOM on large datasets.",
            "correctness": "No pagination, filtering, or sorting exposed to callers.",
            "edge_cases": "Empty table returns [] correctly, but million-row table crashes the process.",
        }),
    ),

    PRTemplate(
        name="insecure_deserialization",
        language="python",
        change_type="feature",
        severity="critical",
        description="Deserialize user-supplied pickle data",
        diff_template="""\
--- a/api/import_data.py
+++ b/api/import_data.py
@@ -0,0 +1,8 @@
+import pickle
+
+@app.route('/import', methods=['POST'])
+def import_data():
+    data = pickle.loads(request.data)
+    return jsonify({"count": len(data)})
""",
        annotations=_clean({
            "security": "pickle.loads on untrusted input allows arbitrary code execution (RCE).",
            "error_handling": "No content-type check, no size limit, no exception handling.",
            "correctness": "len(data) assumes data is a sequence; any other type raises TypeError silently caught by Flask.",
        }),
    ),

    # ---------------------------------------------------------------------------
    # TypeScript templates (12)
    # ---------------------------------------------------------------------------

    PRTemplate(
        name="ts_promise_not_awaited",
        language="typescript",
        change_type="feature",
        severity="high",
        description="Call async function without awaiting the result",
        diff_template="""\
--- a/src/services/user.ts
+++ b/src/services/user.ts
@@ -5,5 +5,10 @@
+async function deleteUser(id: string): Promise<void> {
+  db.delete('users', id);   // missing await
+  logger.info(`Deleted user ${id}`);
+}
""",
        annotations=_clean({
            "correctness": "db.delete returns a Promise; without await the deletion may not complete before the log line runs.",
            "error_handling": "Rejection from db.delete is silently swallowed — unhandled promise rejection.",
        }),
    ),

    PRTemplate(
        name="ts_any_type_escape",
        language="typescript",
        change_type="feature",
        severity="medium",
        description="Use 'any' type to bypass TypeScript checks",
        diff_template="""\
--- a/src/api/handler.ts
+++ b/src/api/handler.ts
@@ -2,5 +2,10 @@
+export function processPayload(payload: any): string {
+  return payload.data.items[0].name;
+}
""",
        annotations=_clean({
            "correctness": "any disables all type safety; runtime crash if payload.data or items is undefined.",
            "edge_cases": "No guard for empty items array — items[0] is undefined.",
            "readability": "Replace any with a proper interface to make the expected shape explicit.",
        }),
    ),

    PRTemplate(
        name="ts_prototype_pollution",
        language="typescript",
        change_type="feature",
        severity="critical",
        description="Merge user-controlled keys into object without guard",
        diff_template="""\
--- a/src/utils/merge.ts
+++ b/src/utils/merge.ts
@@ -0,0 +1,8 @@
+export function mergeConfig(base: Record<string, unknown>, overrides: Record<string, unknown>) {
+  for (const key of Object.keys(overrides)) {
+    (base as any)[key] = overrides[key];
+  }
+  return base;
+}
""",
        annotations=_clean({
            "security": "No check for __proto__ or constructor keys allows prototype pollution attacks.",
            "correctness": "any cast defeats TypeScript safety; use Object.hasOwn to guard.",
        }),
    ),

    PRTemplate(
        name="ts_missing_null_check",
        language="typescript",
        change_type="feature",
        severity="medium",
        description="Access DOM element without null guard",
        diff_template="""\
--- a/src/ui/form.ts
+++ b/src/ui/form.ts
@@ -1,4 +1,8 @@
+export function getInputValue(): string {
+  const el = document.getElementById('email-input');
+  return el.value;
+}
""",
        annotations=_clean({
            "correctness": "getElementById returns HTMLElement | null; .value access throws if element is absent.",
            "edge_cases": "Returns empty string if element is present but user hasn't typed; caller may misinterpret.",
        }),
    ),

    PRTemplate(
        name="ts_forEach_async",
        language="typescript",
        change_type="feature",
        severity="high",
        description="Use forEach with async callback — promises ignored",
        diff_template="""\
--- a/src/jobs/sync.ts
+++ b/src/jobs/sync.ts
@@ -3,5 +3,10 @@
+async function syncAll(ids: string[]): Promise<void> {
+  ids.forEach(async (id) => {
+    await syncItem(id);
+  });
+}
""",
        annotations=_clean({
            "correctness": "forEach does not await async callbacks; all syncItem calls fire in parallel without error handling.",
            "performance": "Should use Promise.all or sequential for-of depending on concurrency requirements.",
            "error_handling": "Rejections from syncItem are silently swallowed by forEach.",
        }),
    ),

    PRTemplate(
        name="ts_no_input_validation",
        language="typescript",
        change_type="feature",
        severity="high",
        description="Express route handler with no input validation",
        diff_template="""\
--- a/src/routes/transfer.ts
+++ b/src/routes/transfer.ts
@@ -2,6 +2,12 @@
+router.post('/transfer', async (req, res) => {
+  const { from, to, amount } = req.body;
+  await transferFunds(from, to, amount);
+  res.json({ success: true });
+});
""",
        annotations=_clean({
            "security": "No authentication or authorization check before funds transfer.",
            "correctness": "amount is not validated as positive number — negative transfer steals funds.",
            "error_handling": "transferFunds errors not caught; Express will return 500 with stack trace.",
            "edge_cases": "from === to case not guarded; missing fields produce undefined args silently.",
        }),
    ),

    PRTemplate(
        name="ts_memory_leak_listener",
        language="typescript",
        change_type="feature",
        severity="medium",
        description="Add event listener without cleanup in React component",
        diff_template="""\
--- a/src/components/Resize.tsx
+++ b/src/components/Resize.tsx
@@ -3,7 +3,12 @@
+export function ResizeTracker() {
+  const [width, setWidth] = React.useState(window.innerWidth);
+  React.useEffect(() => {
+    window.addEventListener('resize', () => setWidth(window.innerWidth));
+  }, []);
+  return <div>{width}</div>;
+}
""",
        annotations=_clean({
            "correctness": "No cleanup function returned from useEffect — listener accumulates on every mount.",
            "performance": "Memory leak and stale closure: setWidth called after unmount causes state update warning.",
        }),
    ),

    PRTemplate(
        name="ts_sql_template_literal",
        language="typescript",
        change_type="feature",
        severity="critical",
        description="Construct SQL query with template literal in TypeScript",
        diff_template="""\
--- a/src/db/users.ts
+++ b/src/db/users.ts
@@ -1,4 +1,8 @@
+export async function findUser(name: string) {
+  const result = await db.query(`SELECT * FROM users WHERE name = '${name}'`);
+  return result.rows[0];
+}
""",
        annotations=_clean({
            "security": "Template literal SQL is injectable — use parameterised queries ($1 placeholders).",
            "edge_cases": "result.rows[0] is undefined if no match; caller receives undefined silently.",
        }),
    ),

    PRTemplate(
        name="ts_optional_chaining_missed",
        language="typescript",
        change_type="feature",
        severity="medium",
        description="Access deeply nested optional property without guard",
        diff_template="""\
--- a/src/analytics/tracker.ts
+++ b/src/analytics/tracker.ts
@@ -2,5 +2,9 @@
+function trackPageView(event: PageEvent) {
+  const label = event.page.meta.title;
+  analytics.track('page_view', { label });
+}
""",
        annotations=_clean({
            "correctness": "event.page or event.page.meta may be undefined; throws at runtime without optional chaining.",
            "edge_cases": "Undefined label is tracked as-is, polluting analytics data.",
        }),
    ),

    PRTemplate(
        name="ts_enum_string_mismatch",
        language="typescript",
        change_type="feature",
        severity="medium",
        description="Compare string to numeric enum value",
        diff_template="""\
--- a/src/models/status.ts
+++ b/src/models/status.ts
@@ -0,0 +1,10 @@
+enum Status { Pending = 0, Active = 1, Closed = 2 }
+
+function isActive(status: string): boolean {
+  return status === Status.Active;
+}
""",
        annotations=_clean({
            "correctness": "Status.Active is 1 (number); comparing to a string always returns false.",
            "api_consistency": "Function signature accepts string but callers pass enum values — type mismatch at boundary.",
        }),
    ),

    PRTemplate(
        name="ts_console_log_production",
        language="typescript",
        change_type="feature",
        severity="low",
        description="Leave debug console.log statements in production code",
        diff_template="""\
--- a/src/services/payment.ts
+++ b/src/services/payment.ts
@@ -5,5 +5,12 @@
+async function processPayment(card: CardDetails) {
+  console.log('Processing payment', card);
+  const result = await stripe.charges.create({ amount: card.amount });
+  console.log('Payment result', result);
+  return result;
+}
""",
        annotations=_clean({
            "security": "CardDetails logged to console may include PAN or CVV — PCI-DSS violation.",
            "readability": "console.log in production code is a code-quality red flag; use a structured logger.",
        }),
    ),

    PRTemplate(
        name="ts_no_rate_limit",
        language="typescript",
        change_type="feature",
        severity="high",
        description="Add password reset endpoint without rate limiting",
        diff_template="""\
--- a/src/routes/auth.ts
+++ b/src/routes/auth.ts
@@ -3,6 +3,12 @@
+router.post('/reset-password', async (req, res) => {
+  const { email } = req.body;
+  const token = await generateResetToken(email);
+  await sendResetEmail(email, token);
+  res.json({ sent: true });
+});
""",
        annotations=_clean({
            "security": "No rate limiting — endpoint is trivially exploitable for email bombing and account enumeration.",
            "correctness": "Returns success even when email is not found — leaks whether account exists.",
            "error_handling": "sendResetEmail failure not caught; silent error leaves user without reset link.",
        }),
    ),

    # ---------------------------------------------------------------------------
    # Go templates (10)
    # ---------------------------------------------------------------------------

    PRTemplate(
        name="go_goroutine_leak",
        language="go",
        change_type="feature",
        severity="high",
        description="Launch goroutine without a way to stop it",
        diff_template="""\
--- a/worker/poller.go
+++ b/worker/poller.go
@@ -5,6 +5,12 @@
+func StartPoller(interval time.Duration) {
+	go func() {
+		for {
+			poll()
+			time.Sleep(interval)
+		}
+	}()
+}
""",
        annotations=_clean({
            "correctness": "Goroutine runs forever with no context cancellation or stop channel — leaks on shutdown.",
            "performance": "Uncontrolled goroutine accumulates if StartPoller is called multiple times.",
            "error_handling": "poll() errors are silently discarded inside the goroutine.",
        }),
    ),

    PRTemplate(
        name="go_nil_pointer",
        language="go",
        change_type="feature",
        severity="high",
        description="Dereference pointer returned from map lookup",
        diff_template="""\
--- a/store/users.go
+++ b/store/users.go
@@ -8,5 +8,10 @@
+func GetUser(id string) string {
+	user := userMap[id]
+	return user.Name
+}
""",
        annotations=_clean({
            "correctness": "Map lookup returns zero value (*User = nil) when key absent; .Name dereferences nil — panic.",
            "edge_cases": "Missing id is the common case in a lookup; must check ok from two-value form.",
        }),
    ),

    PRTemplate(
        name="go_unchecked_error",
        language="go",
        change_type="feature",
        severity="medium",
        description="Ignore error return from file write",
        diff_template="""\
--- a/storage/writer.go
+++ b/storage/writer.go
@@ -3,6 +3,10 @@
+func WriteReport(path string, data []byte) {
+	f, _ := os.Create(path)
+	f.Write(data)
+	f.Close()
+}
""",
        annotations=_clean({
            "error_handling": "os.Create error ignored with _; f is nil if creation fails — f.Write panics.",
            "correctness": "f.Write and f.Close errors also ignored; silent data loss on disk-full or permission error.",
        }),
    ),

    PRTemplate(
        name="go_data_race_map",
        language="go",
        change_type="feature",
        severity="high",
        description="Read and write shared map from multiple goroutines",
        diff_template="""\
--- a/cache/inmemory.go
+++ b/cache/inmemory.go
@@ -0,0 +1,14 @@
+var cache = map[string]string{}
+
+func Set(key, value string) {
+	cache[key] = value
+}
+
+func Get(key string) string {
+	return cache[key]
+}
""",
        annotations=_clean({
            "correctness": "Concurrent map read/write is undefined behaviour in Go — will panic with 'concurrent map read and map write'.",
            "performance": "Use sync.Map or a mutex-protected wrapper for thread-safe access.",
        }),
    ),

    PRTemplate(
        name="go_integer_division",
        language="go",
        change_type="feature",
        severity="medium",
        description="Compute percentage using integer division",
        diff_template="""\
--- a/metrics/rate.go
+++ b/metrics/rate.go
@@ -0,0 +1,6 @@
+func SuccessRate(success, total int) int {
+	return success / total * 100
+}
""",
        annotations=_clean({
            "correctness": "Integer division truncates before multiplying — SuccessRate(1, 3) returns 0, not 33.",
            "edge_cases": "total == 0 causes divide-by-zero panic; not guarded.",
        }),
    ),

    PRTemplate(
        name="go_context_ignored",
        language="go",
        change_type="feature",
        severity="medium",
        description="Accept context parameter but never use it",
        diff_template="""\
--- a/db/query.go
+++ b/db/query.go
@@ -3,5 +3,9 @@
+func FetchRecords(ctx context.Context, ids []int) ([]Record, error) {
+	rows, err := db.Query("SELECT * FROM records WHERE id = ANY($1)", ids)
+	return scanRows(rows, err)
+}
""",
        annotations=_clean({
            "correctness": "ctx is accepted but never passed to db.QueryContext — cancellation and deadlines are ignored.",
            "performance": "Long-running query cannot be cancelled by the caller; causes goroutine leaks on timeout.",
        }),
    ),

    PRTemplate(
        name="go_slice_append_aliasing",
        language="go",
        change_type="feature",
        severity="medium",
        description="Return modified slice that shares backing array",
        diff_template="""\
--- a/transform/filter.go
+++ b/transform/filter.go
@@ -0,0 +1,8 @@
+func Filter(items []string, keep string) []string {
+	result := items[:0]
+	for _, item := range items {
+		if item == keep {
+			result = append(result, item)
+		}
+	}
+	return result
+}
""",
        annotations=_clean({
            "correctness": "items[:0] shares the backing array with items; appending to result overwrites original slice elements.",
            "edge_cases": "Empty items slice is handled correctly but the aliasing bug is invisible in unit tests.",
        }),
    ),

    PRTemplate(
        name="go_http_timeout_missing",
        language="go",
        change_type="feature",
        severity="high",
        description="Create HTTP client without timeout",
        diff_template="""\
--- a/client/http.go
+++ b/client/http.go
@@ -0,0 +1,10 @@
+var httpClient = &http.Client{}
+
+func Get(url string) ([]byte, error) {
+	resp, err := httpClient.Get(url)
+	if err != nil {
+		return nil, err
+	}
+	defer resp.Body.Close()
+	return io.ReadAll(resp.Body)
+}
""",
        annotations=_clean({
            "performance": "http.Client with no Timeout will wait forever on a slow server — goroutine and connection leak.",
            "correctness": "resp.Body.Close() is deferred even on error paths where Body may be nil.",
        }),
    ),

    PRTemplate(
        name="go_string_conversion_loop",
        language="go",
        change_type="feature",
        severity="medium",
        description="Build large string with += in a loop",
        diff_template="""\
--- a/render/csv.go
+++ b/render/csv.go
@@ -0,0 +1,8 @@
+func BuildCSV(rows [][]string) string {
+	result := ""
+	for _, row := range rows {
+		result += strings.Join(row, ",") + "\\n"
+	}
+	return result
+}
""",
        annotations=_clean({
            "performance": "String concatenation with += is O(n²) — use strings.Builder for O(n) performance.",
            "readability": "strings.Builder or bytes.Buffer is the idiomatic Go pattern for this operation.",
        }),
    ),

    PRTemplate(
        name="go_panic_in_library",
        language="go",
        change_type="feature",
        severity="high",
        description="Use panic for expected error conditions in library code",
        diff_template="""\
--- a/config/loader.go
+++ b/config/loader.go
@@ -0,0 +1,10 @@
+func LoadConfig(path string) Config {
+	data, err := os.ReadFile(path)
+	if err != nil {
+		panic(fmt.Sprintf("config not found: %s", err))
+	}
+	var cfg Config
+	json.Unmarshal(data, &cfg)
+	return cfg
+}
""",
        annotations=_clean({
            "error_handling": "panic in library code is poor practice — callers cannot recover; return (Config, error) instead.",
            "correctness": "json.Unmarshal error ignored with blank identifier pattern.",
        }),
    ),

    # ---------------------------------------------------------------------------
    # Java templates (10)
    # ---------------------------------------------------------------------------

    PRTemplate(
        name="java_thread_unsafe_singleton",
        language="java",
        change_type="feature",
        severity="high",
        description="Implement singleton with non-atomic lazy initialization",
        diff_template="""\
--- a/src/main/java/com/acme/Config.java
+++ b/src/main/java/com/acme/Config.java
@@ -3,8 +3,14 @@
+public class Config {
+    private static Config instance;
+
+    public static Config getInstance() {
+        if (instance == null) {
+            instance = new Config();
+        }
+        return instance;
+    }
+}
""",
        annotations=_clean({
            "correctness": "Check-then-act on instance is not atomic — two threads can both see null and create separate instances.",
            "performance": "Use enum singleton or double-checked locking with volatile for thread-safe lazy init.",
        }),
    ),

    PRTemplate(
        name="java_resource_leak",
        language="java",
        change_type="feature",
        severity="high",
        description="Open InputStream without try-with-resources",
        diff_template="""\
--- a/src/main/java/com/acme/FileReader.java
+++ b/src/main/java/com/acme/FileReader.java
@@ -4,8 +4,12 @@
+public String readFile(String path) throws IOException {
+    InputStream is = new FileInputStream(path);
+    byte[] bytes = is.readAllBytes();
+    return new String(bytes);
+}
""",
        annotations=_clean({
            "correctness": "InputStream not closed if readAllBytes throws — file descriptor leak.",
            "error_handling": "Use try-with-resources to guarantee close() even on exception.",
        }),
    ),

    PRTemplate(
        name="java_raw_types",
        language="java",
        change_type="feature",
        severity="medium",
        description="Use raw generic type instead of parameterized",
        diff_template="""\
--- a/src/main/java/com/acme/DataStore.java
+++ b/src/main/java/com/acme/DataStore.java
@@ -2,7 +2,12 @@
+public class DataStore {
+    private List items = new ArrayList();
+
+    public void add(Object item) {
+        items.add(item);
+    }
+}
""",
        annotations=_clean({
            "correctness": "Raw List bypasses generics — ClassCastException at runtime, not compile time.",
            "readability": "Use List<T> or List<Object> explicitly; raw types are a Java 5 legacy anti-pattern.",
        }),
    ),

    PRTemplate(
        name="java_string_equals",
        language="java",
        change_type="bugfix",
        severity="medium",
        description="Compare String objects with == instead of .equals()",
        diff_template="""\
--- a/src/main/java/com/acme/Auth.java
+++ b/src/main/java/com/acme/Auth.java
@@ -5,5 +5,9 @@
+boolean isAdmin(String role) {
+    return role == "admin";
+}
""",
        annotations=_clean({
            "correctness": "== compares object references; two separate String objects with value 'admin' compare false.",
            "edge_cases": "role == null would throw NullPointerException; use \"admin\".equals(role) instead.",
        }),
    ),

    PRTemplate(
        name="java_swallowed_exception",
        language="java",
        change_type="feature",
        severity="high",
        description="Catch Exception and do nothing with it",
        diff_template="""\
--- a/src/main/java/com/acme/Processor.java
+++ b/src/main/java/com/acme/Processor.java
@@ -6,8 +6,14 @@
+public void process(Event event) {
+    try {
+        handler.handle(event);
+    } catch (Exception e) {
+        // TODO: handle this properly
+    }
+}
""",
        annotations=_clean({
            "error_handling": "Silent catch swallows exceptions — failures are invisible; at minimum log the exception.",
            "correctness": "TODO comment signals unfinished error handling — not production-ready.",
        }),
    ),

    PRTemplate(
        name="java_sql_concat",
        language="java",
        change_type="feature",
        severity="critical",
        description="Build JDBC query with string concatenation",
        diff_template="""\
--- a/src/main/java/com/acme/UserDAO.java
+++ b/src/main/java/com/acme/UserDAO.java
@@ -4,6 +4,10 @@
+public User findByName(String name) throws SQLException {
+    String sql = "SELECT * FROM users WHERE name = '" + name + "'";
+    ResultSet rs = conn.createStatement().executeQuery(sql);
+    return rs.next() ? mapRow(rs) : null;
+}
""",
        annotations=_clean({
            "security": "String concatenation in SQL is injectable — use PreparedStatement with ? placeholders.",
            "correctness": "ResultSet and Statement not closed after use — resource leak.",
        }),
    ),

    PRTemplate(
        name="java_integer_overflow",
        language="java",
        change_type="feature",
        severity="medium",
        description="Multiply two ints without casting to long",
        diff_template="""\
--- a/src/main/java/com/acme/Calculator.java
+++ b/src/main/java/com/acme/Calculator.java
@@ -2,5 +2,8 @@
+public long totalBytes(int fileSizeMb, int fileCount) {
+    return fileSizeMb * fileCount * 1024 * 1024;
+}
""",
        annotations=_clean({
            "correctness": "Multiplication is performed in int before assignment to long — overflows for files > 2GB.",
            "edge_cases": "Cast at least one operand to long: (long) fileSizeMb * fileCount * 1024 * 1024.",
        }),
    ),

    PRTemplate(
        name="java_static_mutable_field",
        language="java",
        change_type="feature",
        severity="high",
        description="Expose mutable static list as public field",
        diff_template="""\
--- a/src/main/java/com/acme/Registry.java
+++ b/src/main/java/com/acme/Registry.java
@@ -2,5 +2,7 @@
+public class Registry {
+    public static List<String> handlers = new ArrayList<>();
+}
""",
        annotations=_clean({
            "correctness": "Public mutable static field can be cleared or replaced by any caller — global mutable state.",
            "api_consistency": "Expose via getter returning Collections.unmodifiableList() or use a proper registration API.",
        }),
    ),

    PRTemplate(
        name="java_deprecated_api",
        language="java",
        change_type="feature",
        severity="low",
        description="Use deprecated Date constructor for timestamp",
        diff_template="""\
--- a/src/main/java/com/acme/Event.java
+++ b/src/main/java/com/acme/Event.java
@@ -1,5 +1,9 @@
+import java.util.Date;
+
+public class Event {
+    public Date timestamp = new Date(2024, 1, 1);
+}
""",
        annotations=_clean({
            "correctness": "new Date(int year, int month, int day) is deprecated and year is offset by 1900 — actual year is 3924.",
            "dependency_hygiene": "Use java.time.LocalDate or java.time.Instant instead of legacy java.util.Date.",
        }),
    ),

    PRTemplate(
        name="java_finalizer_misuse",
        language="java",
        change_type="feature",
        severity="medium",
        description="Override finalize() for resource cleanup",
        diff_template="""\
--- a/src/main/java/com/acme/Connection.java
+++ b/src/main/java/com/acme/Connection.java
@@ -5,7 +5,12 @@
+@Override
+protected void finalize() throws Throwable {
+    socket.close();
+    super.finalize();
+}
""",
        annotations=_clean({
            "correctness": "finalize() is deprecated in Java 9+ and unreliable — GC may never call it.",
            "performance": "Objects with finalizers are promoted to the finalization queue, adding GC pressure.",
            "api_consistency": "Implement AutoCloseable and use try-with-resources instead.",
        }),
    ),

    # ---------------------------------------------------------------------------
    # Rust templates (8)
    # ---------------------------------------------------------------------------

    PRTemplate(
        name="rust_unwrap_in_production",
        language="rust",
        change_type="feature",
        severity="high",
        description="Use .unwrap() on Result in request handler",
        diff_template="""\
--- a/src/handlers/upload.rs
+++ b/src/handlers/upload.rs
@@ -3,6 +3,10 @@
+pub async fn upload(body: Bytes) -> impl Responder {
+    let path = std::str::from_utf8(&body).unwrap();
+    let content = std::fs::read_to_string(path).unwrap();
+    HttpResponse::Ok().body(content)
+}
""",
        annotations=_clean({
            "error_handling": "Two .unwrap() calls will panic on invalid UTF-8 or file not found — crashing the server process.",
            "correctness": "Reading arbitrary user-supplied paths is a path traversal vulnerability.",
            "security": "Attacker can read any file readable by the server user via path traversal.",
        }),
    ),

    PRTemplate(
        name="rust_clone_instead_of_borrow",
        language="rust",
        change_type="feature",
        severity="low",
        description="Clone large string to avoid borrow checker instead of using reference",
        diff_template="""\
--- a/src/services/mailer.rs
+++ b/src/services/mailer.rs
@@ -3,6 +3,10 @@
+fn send_welcome(user: &User) {
+    let email = user.email.clone();
+    let name = user.name.clone();
+    mailer.send(email, format!("Welcome {}", name));
+}
""",
        annotations=_clean({
            "performance": "Unnecessary clone of email and name strings; mailer.send should accept &str or references.",
            "readability": "Using .clone() to sidestep the borrow checker is a code smell — redesign to use borrows.",
        }),
    ),

    PRTemplate(
        name="rust_integer_overflow_debug",
        language="rust",
        change_type="feature",
        severity="medium",
        description="Arithmetic that overflows silently in release builds",
        diff_template="""\
--- a/src/metrics/counter.rs
+++ b/src/metrics/counter.rs
@@ -0,0 +1,7 @@
+pub struct Counter(u8);
+
+impl Counter {
+    pub fn increment(&mut self) { self.0 += 1; }
+    pub fn value(&self) -> u8 { self.0 }
+}
""",
        annotations=_clean({
            "correctness": "u8 overflows at 256; in debug mode panics, in release mode wraps silently to 0.",
            "edge_cases": "Use u64, usize, or checked_add() to avoid wrap-around depending on expected range.",
        }),
    ),

    PRTemplate(
        name="rust_blocking_in_async",
        language="rust",
        change_type="feature",
        severity="high",
        description="Call std::thread::sleep inside async function",
        diff_template="""\
--- a/src/jobs/poller.rs
+++ b/src/jobs/poller.rs
@@ -2,6 +2,10 @@
+pub async fn poll_loop() {
+    loop {
+        do_work().await;
+        std::thread::sleep(Duration::from_secs(5));
+    }
+}
""",
        annotations=_clean({
            "performance": "std::thread::sleep blocks the async executor thread — starves all other tasks on that thread.",
            "correctness": "Use tokio::time::sleep or async_std::task::sleep for async-compatible delay.",
        }),
    ),

    PRTemplate(
        name="rust_string_allocation_loop",
        language="rust",
        change_type="feature",
        severity="medium",
        description="Concatenate strings in loop with + operator",
        diff_template="""\
--- a/src/render/builder.rs
+++ b/src/render/builder.rs
@@ -0,0 +1,8 @@
+pub fn build_report(lines: &[String]) -> String {
+    let mut result = String::new();
+    for line in lines {
+        result = result + line + "\\n";
+    }
+    result
+}
""",
        annotations=_clean({
            "performance": "result + line moves and reallocates result on every iteration — O(n²) allocations.",
            "readability": "Use result.push_str(line); result.push('\\n'); or lines.join(\"\\n\") for idiomatic Rust.",
        }),
    ),

    PRTemplate(
        name="rust_mutex_deadlock",
        language="rust",
        change_type="feature",
        severity="high",
        description="Lock same Mutex twice in the same thread",
        diff_template="""\
--- a/src/state/store.rs
+++ b/src/state/store.rs
@@ -4,8 +4,14 @@
+pub fn update_and_log(store: &Mutex<HashMap<String, u64>>, key: &str) {
+    let mut map = store.lock().unwrap();
+    let count = get_count(store, key);  // calls store.lock() again
+    map.insert(key.to_string(), count + 1);
+}
""",
        annotations=_clean({
            "correctness": "get_count acquires the same Mutex lock — std::sync::Mutex is not reentrant, causing a deadlock.",
            "performance": "Deadlock hangs the thread permanently; tokio::sync::Mutex also deadlocks in this pattern.",
        }),
    ),

    PRTemplate(
        name="rust_clippy_needless_return",
        language="rust",
        change_type="refactor",
        severity="low",
        description="Add unnecessary explicit return statements throughout module",
        diff_template="""\
--- a/src/utils/math.rs
+++ b/src/utils/math.rs
@@ -0,0 +1,12 @@
+pub fn square(x: i64) -> i64 {
+    return x * x;
+}
+
+pub fn cube(x: i64) -> i64 {
+    return x * x * x;
+}
""",
        annotations=_clean({
            "readability": "Explicit return at end of function violates Rust idiom — clippy::needless_return lint fires.",
            "OK:correctness": "Logic is correct; style issue only.",
        }),
    ),

    PRTemplate(
        name="rust_error_type_mismatch",
        language="rust",
        change_type="feature",
        severity="medium",
        description="Return incompatible error types from functions in same module",
        diff_template="""\
--- a/src/pipeline/steps.rs
+++ b/src/pipeline/steps.rs
@@ -0,0 +1,12 @@
+pub fn step_one() -> Result<(), std::io::Error> {
+    Ok(std::fs::write("out.txt", b"data")?)
+}
+
+pub fn step_two() -> Result<(), serde_json::Error> {
+    Ok(serde_json::to_writer(std::io::stdout(), &"hello")?)
+}
+
+pub fn run() -> Result<(), String> {
+    step_one().map_err(|e| e.to_string())?;
+    step_two().map_err(|e| e.to_string())?;
+    Ok(())
+}
""",
        annotations=_clean({
            "api_consistency": "Three functions in the same pipeline return three different error types — inconsistent module interface.",
            "correctness": "Use a shared error enum or anyhow::Error for consistent error propagation across pipeline steps.",
        }),
    ),
]


def get_all_templates() -> list[PRTemplate]:
    return TEMPLATES


def get_template_by_name(name: str) -> PRTemplate | None:
    return next((t for t in TEMPLATES if t.name == name), None)
