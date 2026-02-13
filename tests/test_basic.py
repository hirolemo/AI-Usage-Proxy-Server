"""
Basic tests for the AI Usage Proxy Server.

Run with: pytest tests/test_basic.py -v
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from main import app


@pytest.fixture(scope="module")
def client():
    """Create a test client with proper lifespan handling."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def test_api_key(client):
    """Create a test user via admin API and return their API key."""
    response = client.post(
        "/admin/users",
        headers={"Authorization": "Bearer admin-secret-key"},
        json={"user_id": "test-user"},
    )
    if response.status_code == 200:
        return response.json()["api_key"]

    # User already exists — find their key from the user list
    resp = client.get(
        "/admin/users",
        headers={"Authorization": "Bearer admin-secret-key"},
    )
    for user in resp.json()["users"]:
        if user["user_id"] == "test-user":
            return user["api_key"]

    raise RuntimeError("Could not create or find test-user")


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_root_endpoint(self, client):
        """Test the root endpoint returns status."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "service" in data

    def test_health_endpoint(self, client):
        """Test the health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestAuthentication:
    """Test authentication middleware."""

    def test_missing_auth_header(self, client):
        """Test that requests without auth header are rejected."""
        response = client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 401

    def test_invalid_auth_header_format(self, client):
        """Test that invalid auth header format is rejected."""
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Basic invalid"},
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 401

    def test_invalid_api_key(self, client):
        """Test that invalid API key is rejected."""
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer invalid-key"},
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert response.status_code == 401


class TestAdminEndpoints:
    """Test admin API endpoints."""

    def test_admin_missing_auth(self, client):
        """Test admin endpoints require auth."""
        response = client.get("/admin/users")
        assert response.status_code == 401

    def test_admin_invalid_key(self, client):
        """Test admin endpoints reject invalid admin key."""
        response = client.get(
            "/admin/users",
            headers={"Authorization": "Bearer wrong-admin-key"},
        )
        assert response.status_code == 403

    def test_admin_create_user(self, client):
        """Test creating a user via admin API."""
        response = client.post(
            "/admin/users",
            headers={"Authorization": "Bearer admin-secret-key"},
            json={"user_id": "admin-test-user"},
        )
        # Either 200 (created) or 409 (already exists)
        assert response.status_code in [200, 409]

    def test_admin_list_users(self, client):
        """Test listing users via admin API."""
        response = client.get(
            "/admin/users",
            headers={"Authorization": "Bearer admin-secret-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "users" in data


class TestChatCompletions:
    """Test chat completion endpoints (mocked)."""

    @patch("app.services.ollama_client.ollama_client.chat_completion")
    def test_chat_completion_non_streaming(
        self, mock_completion, client, test_api_key
    ):
        """Test non-streaming chat completion."""
        mock_completion.return_value = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "llama3.2:1b",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }

        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {test_api_key}"},
            json={
                "model": "llama3.2:1b",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "Hello!"
        assert data["usage"]["total_tokens"] == 15


class TestUsageEndpoints:
    """Test usage tracking endpoints."""

    def test_get_usage(self, client, test_api_key):
        """Test getting user's usage."""
        response = client.get(
            "/v1/usage",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_tokens" in data
        assert "by_model" in data

    def test_get_usage_summary(self, client, test_api_key):
        """Test getting usage summary."""
        response = client.get(
            "/v1/usage/summary",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_tokens" in data
        assert "by_model" in data


class TestRequestHistory:
    """Test request history endpoint."""

    def test_get_request_history_empty(self, client, test_api_key):
        """Test getting request history when empty returns valid structure."""
        response = client.get(
            "/v1/usage/history",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "records" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "has_more" in data
        assert isinstance(data["records"], list)

    def test_get_request_history_pagination_params(self, client, test_api_key):
        """Test that limit and offset are respected."""
        response = client.get(
            "/v1/usage/history?limit=5&offset=0",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5
        assert data["offset"] == 0

    def test_get_request_history_invalid_limit(self, client, test_api_key):
        """Test that invalid limit returns 422."""
        response = client.get(
            "/v1/usage/history?limit=0",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )
        assert response.status_code == 422

    @patch("app.services.ollama_client.ollama_client.chat_completion")
    def test_request_history_after_completion(
        self, mock_completion, client, test_api_key
    ):
        """Test that prompt_preview appears in history after a completion."""
        mock_completion.return_value = {
            "id": "chatcmpl-history-test",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "llama3.2:1b",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hi there!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 8,
                "completion_tokens": 4,
                "total_tokens": 12,
            },
        }

        # Make a completion request
        client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {test_api_key}"},
            json={
                "model": "llama3.2:1b",
                "messages": [{"role": "user", "content": "Tell me about history"}],
            },
        )

        # Check request history
        response = client.get(
            "/v1/usage/history?limit=1",
            headers={"Authorization": f"Bearer {test_api_key}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["records"]) >= 1
        latest = data["records"][0]
        assert latest["prompt_preview"] == "Tell me about history"
        assert latest["model"] == "llama3.2:1b"
        assert latest["total_tokens"] == 12


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
