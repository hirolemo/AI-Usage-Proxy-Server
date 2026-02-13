"""
Tests for streaming functionality.

Run with: pytest tests/test_streaming.py -v

NOTE: These tests require Ollama to be running locally.
"""

import os

import pytest
from openai import OpenAI


# Skip these tests if Ollama is not available
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS", "true").lower() == "true",
    reason="Integration tests disabled. Set SKIP_INTEGRATION_TESTS=false to run.",
)


@pytest.fixture
def openai_client():
    """Create an OpenAI client pointing to our proxy.

    Set TEST_API_KEY env var to your user's API key.
    """
    api_key = os.environ.get("TEST_API_KEY", "sk-test-user")
    return OpenAI(
        base_url="http://localhost:8000/v1",
        api_key=api_key,
    )


class TestStreaming:
    """Test streaming chat completions."""

    def test_streaming_response(self, openai_client):
        """Test that streaming responses work correctly."""
        collected_content = []

        stream = openai_client.chat.completions.create(
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "Count from 1 to 5"}],
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                collected_content.append(chunk.choices[0].delta.content)

        full_response = "".join(collected_content)
        assert len(full_response) > 0
        print(f"Streaming response: {full_response}")

    def test_streaming_token_counting(self, openai_client):
        """Test that tokens are counted during streaming."""
        import httpx

        api_key = os.environ.get("TEST_API_KEY", "sk-test-user")

        # Get initial usage
        initial_usage = httpx.get(
            "http://localhost:8000/v1/usage",
            headers={"Authorization": f"Bearer {api_key}"},
        ).json()

        # Make streaming request
        stream = openai_client.chat.completions.create(
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "Say hello"}],
            stream=True,
        )

        # Consume the stream
        for chunk in stream:
            pass

        # Check usage increased
        final_usage = httpx.get(
            "http://localhost:8000/v1/usage",
            headers={"Authorization": f"Bearer {api_key}"},
        ).json()

        assert final_usage["total_tokens"] > initial_usage["total_tokens"]
        print(
            f"Tokens used: {final_usage['total_tokens'] - initial_usage['total_tokens']}"
        )


class TestNonStreaming:
    """Test non-streaming chat completions."""

    def test_non_streaming_response(self, openai_client):
        """Test that non-streaming responses work correctly."""
        response = openai_client.chat.completions.create(
            model="llama3.2:1b",
            messages=[{"role": "user", "content": "What is 2+2?"}],
            stream=False,
        )

        assert response.choices[0].message.content
        assert response.usage.total_tokens > 0
        print(f"Response: {response.choices[0].message.content}")
        print(f"Tokens: {response.usage.total_tokens}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
