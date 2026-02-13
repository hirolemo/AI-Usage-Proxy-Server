"""
Load testing for the AI Usage Proxy Server.

Run with locust:
    locust -f tests/test_load.py --host=http://localhost:8000 --users=100 --spawn-rate=10

Or run the quick test:
    python tests/test_load.py
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from locust import HttpUser, task, between
    LOCUST_AVAILABLE = True
except ImportError:
    LOCUST_AVAILABLE = False


if LOCUST_AVAILABLE:

    class ProxyUser(HttpUser):
        """Simulated user for load testing."""

        wait_time = between(1, 3)  # Wait 1-3 seconds between tasks

        def on_start(self):
            """Set up user with API key."""
            # In real testing, you'd get this from admin API or config
            self.api_key = os.environ.get("TEST_API_KEY", "sk-test-user")
            self.headers = {"Authorization": f"Bearer {self.api_key}"}

        @task(10)
        def chat_completion(self):
            """Test chat completion endpoint (most common request)."""
            self.client.post(
                "/v1/chat/completions",
                headers=self.headers,
                json={
                    "model": "llama3.2:1b",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 10,
                },
            )

        @task(3)
        def get_usage(self):
            """Test usage endpoint."""
            self.client.get("/v1/usage", headers=self.headers)

        @task(1)
        def health_check(self):
            """Test health endpoint."""
            self.client.get("/health")


def run_quick_load_test():
    """Run a quick load test without locust."""
    import asyncio
    import httpx
    import time
    from concurrent.futures import ThreadPoolExecutor

    print("Running quick load test...")
    print("Make sure the proxy server is running on localhost:8000")
    print()

    BASE_URL = "http://localhost:8000"
    API_KEY = os.environ.get("TEST_API_KEY", "sk-test-user")
    MODEL = os.environ.get("TEST_MODEL", "llama3.2:1b")
    HEADERS = {"Authorization": f"Bearer {API_KEY}"}

    num_requests = 50
    successful = 0
    failed = 0
    latencies = []

    def make_request(i):
        nonlocal successful, failed
        try:
            start = time.time()
            response = httpx.post(
                f"{BASE_URL}/v1/chat/completions",
                headers=HEADERS,
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": f"Say {i}"}],
                    "max_tokens": 5,
                },
                timeout=60.0,
            )
            elapsed = time.time() - start
            latencies.append(elapsed)

            if response.status_code == 200:
                successful += 1
            else:
                failed += 1
                print(f"Request {i} failed: {response.status_code}")
        except Exception as e:
            failed += 1
            print(f"Request {i} error: {e}")

    print(f"Sending {num_requests} requests concurrently...")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(make_request, range(num_requests))

    total_time = time.time() - start_time

    print()
    print("=" * 50)
    print("Load Test Results")
    print("=" * 50)
    print(f"Total requests: {num_requests}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total time: {total_time:.2f}s")
    print(f"Requests/second: {num_requests / total_time:.2f}")
    if latencies:
        print(f"Average latency: {sum(latencies) / len(latencies):.2f}s")
        print(f"Min latency: {min(latencies):.2f}s")
        print(f"Max latency: {max(latencies):.2f}s")


if __name__ == "__main__":
    run_quick_load_test()
