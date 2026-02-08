"""
Tests for vision model support.

Run with: pytest tests/test_vision.py -v

NOTE: These tests require Ollama to be running with a vision model (e.g., moondream).
"""

import pytest
from openai import OpenAI
import base64
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Skip these tests if Ollama is not available
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS", "true").lower() == "true",
    reason="Integration tests disabled. Set SKIP_INTEGRATION_TESTS=false to run.",
)


@pytest.fixture
def openai_client():
    """Create an OpenAI client pointing to our proxy."""
    return OpenAI(
        base_url="http://localhost:8000/v1",
        api_key="sk-test-user",  # Replace with actual API key
    )


class TestVisionModel:
    """Test vision model functionality."""

    def test_vision_with_url(self, openai_client):
        """Test vision model with image URL."""
        response = openai_client.chat.completions.create(
            model="moondream",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe this image briefly."},
                        {
                            "type": "image_url",
                            "image_url": {"url": "https://picsum.photos/200"},
                        },
                    ],
                }
            ],
        )

        assert response.choices[0].message.content
        print(f"Vision response: {response.choices[0].message.content}")

    def test_vision_with_base64(self, openai_client):
        """Test vision model with base64-encoded image."""
        # Create a simple test image (1x1 red pixel PNG)
        # This is a minimal valid PNG file
        red_pixel_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
        )
        base64_image = base64.b64encode(red_pixel_png).decode("utf-8")

        response = openai_client.chat.completions.create(
            model="moondream",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What color is this image?"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
        )

        assert response.choices[0].message.content
        print(f"Vision response (base64): {response.choices[0].message.content}")

    def test_vision_streaming(self, openai_client):
        """Test vision model with streaming."""
        collected_content = []

        stream = openai_client.chat.completions.create(
            model="moondream",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What do you see?"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "https://picsum.photos/100"},
                        },
                    ],
                }
            ],
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                collected_content.append(chunk.choices[0].delta.content)

        full_response = "".join(collected_content)
        assert len(full_response) > 0
        print(f"Vision streaming response: {full_response}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
