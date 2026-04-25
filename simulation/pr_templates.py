"""Synthetic PR templates covering the full spectrum of code quality issues.

Each template defines the shape of a pull request: language, change type,
intentional issues seeded into the diff, and a ground-truth expected_findings
list that the evaluator uses to score reviewer agreement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PRTemplate:
    name: str
    language: str
    change_type: str  # feature | bugfix | refactor | dependency | docs
    description: str
    diff_template: str          # Python format string, filled by generator
    expected_findings: list[str]  # ground-truth issues a good reviewer should find
    severity: str = "medium"   # low | medium | high | critical


TEMPLATES: list[PRTemplate] = [
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
        expected_findings=["security", "correctness"],
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
        expected_findings=["performance"],
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
        expected_findings=["error_handling", "edge_cases"],
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
        expected_findings=["security", "dependency_hygiene"],
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
        expected_findings=["test_coverage", "edge_cases"],
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
        expected_findings=[],  # no issues — agent should approve
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
        expected_findings=["breaking_changes", "api_consistency"],
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
+    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
+    return bool(re.match(pattern, email))
+
+def send_notification(email: str, message: str) -> None:
+    if is_valid_email(email):
+        smtp_client.send(email, message)
""",
        expected_findings=["code_duplication"],
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
        expected_findings=["performance", "error_handling"],
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
        expected_findings=["edge_cases", "correctness"],
    ),
]


def get_all_templates() -> list[PRTemplate]:
    return TEMPLATES


def get_template_by_name(name: str) -> PRTemplate | None:
    return next((t for t in TEMPLATES if t.name == name), None)
