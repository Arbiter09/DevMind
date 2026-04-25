"""Unit tests for the GitHub webhook handler."""
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_payload(action: str = "opened", pr_number: int = 42) -> dict:
    return {
        "action": action,
        "number": pr_number,
        "repository": {"full_name": "owner/repo"},
        "pull_request": {"title": "Test PR"},
    }


def _sign_payload(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestGitHubWebhook:
    @pytest.fixture
    def client(self):
        from api.main import create_app
        app = create_app()
        # Disable startup workers for unit tests
        app.router.on_startup.clear()
        return TestClient(app, raise_server_exceptions=True)

    def test_non_pr_event_ignored(self, client):
        with patch("api.webhooks.WEBHOOK_SECRET", ""):
            resp = client.post(
                "/webhooks/github",
                json=_make_payload(),
                headers={"X-GitHub-Event": "push"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_ignored_action_not_queued(self, client):
        payload = _make_payload(action="closed")
        with patch("api.webhooks.WEBHOOK_SECRET", ""):
            resp = client.post(
                "/webhooks/github",
                json=payload,
                headers={"X-GitHub-Event": "pull_request"},
            )
        assert resp.json()["status"] == "ignored"

    def test_opened_pr_queued(self, client):
        payload = _make_payload(action="opened")
        with (
            patch("api.webhooks.WEBHOOK_SECRET", ""),
            patch("api.webhooks.get_job_queue") as mock_queue_factory,
        ):
            mock_queue = AsyncMock()
            mock_queue.enqueue.return_value = "1-1"
            mock_queue_factory.return_value = mock_queue

            resp = client.post(
                "/webhooks/github",
                json=payload,
                headers={"X-GitHub-Event": "pull_request"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert "job_id" in data

    def test_synchronize_pr_queued(self, client):
        payload = _make_payload(action="synchronize")
        with (
            patch("api.webhooks.WEBHOOK_SECRET", ""),
            patch("api.webhooks.get_job_queue") as mock_queue_factory,
        ):
            mock_queue = AsyncMock()
            mock_queue.enqueue.return_value = "1-2"
            mock_queue_factory.return_value = mock_queue

            resp = client.post(
                "/webhooks/github",
                json=payload,
                headers={"X-GitHub-Event": "pull_request"},
            )
        assert resp.json()["status"] == "queued"

    def test_invalid_signature_rejected(self, client):
        payload = _make_payload()
        body = json.dumps(payload).encode()
        with patch("api.webhooks.WEBHOOK_SECRET", "real-secret"):
            resp = client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": "sha256=bad_signature",
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 401

    def test_valid_signature_accepted(self, client):
        secret = "test-secret"
        payload = _make_payload(action="opened")
        body = json.dumps(payload).encode()
        sig = _sign_payload(body, secret)

        with (
            patch("api.webhooks.WEBHOOK_SECRET", secret),
            patch("api.webhooks.get_job_queue") as mock_queue_factory,
        ):
            mock_queue = AsyncMock()
            mock_queue.enqueue.return_value = "1-3"
            mock_queue_factory.return_value = mock_queue

            resp = client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
