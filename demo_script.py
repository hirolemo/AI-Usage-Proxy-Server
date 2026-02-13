"""
Demo: OpenAI SDK compatibility with AI Usage Proxy Server.

Shows that the standard OpenAI Python SDK works unmodified —
just change the base_url.

Usage:
    python demo_script.py
    TEST_API_KEY=sk-your-key python demo_script.py
"""

import base64
import os

from openai import OpenAI

API_KEY = os.environ.get("TEST_API_KEY", "sk-test-user")
MODEL = os.environ.get("TEST_MODEL", "llama3.2:1b")

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key=API_KEY,
)

# Non-streaming
print("=== Non-Streaming ===")
response = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": "What is 2+2? Answer in one sentence."}],
)
print(f"Response: {response.choices[0].message.content}")
print(f"Tokens: {response.usage.total_tokens}")

# Streaming
print("\n=== Streaming ===")
print("Response: ", end="", flush=True)
for chunk in client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "user", "content": "Count from 1 to 5"}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="", flush=True)
print()

# Vision with moondream
print("\n=== Vision (moondream) ===")
with open("photo.jpg", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode("utf-8")

response = client.chat.completions.create(
    model="moondream",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What is in this image?"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                },
            ],
        }
    ],
)
print(f"Response: {response.choices[0].message.content}")
print(f"Tokens: {response.usage.total_tokens}")
