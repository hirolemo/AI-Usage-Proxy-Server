"""
Basic tests for the AI Usage Proxy Server.

Run with: pytest tests/test_basic.py -v
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
from app.database import init_db, create_user, get_db


@pytest.fixture(scope="module")
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(scope="module")
def test_api_key():
    """Create a test user and return their API key."""
    import asyncio

    async def setup():
        await init_db()
        try:
            _, api_key = await create_user("test-user")
            return api_key
        except Exception:
            # User might already exist
            async with get_db() as db:
                cursor = await db.execute(
                    "SELECT api_key FROM users WHERE id = ?", ("test-user",)
                )
                row = await cursor.fetchone()
                return row["api_key"] if row else None

    return asyncio.get_event_loop().run_until_complete(setup())


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
