"""
Mock Ollama server that responds instantly.
Used for load testing the proxy without real LLM inference.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    return JSONResponse({
        "model": body.get("model", "llama3.2:1b"),
        "message": {"role": "assistant", "content": "Mock response."},
        "done": True,
        "eval_count": 5,
        "prompt_eval_count": 10,
    })


@app.get("/api/tags")
async def tags():
    return {
        "models": [
            {"name": "llama3.2:1b"},
            {"name": "moondream:latest"},
        ]
    }


if __name__ == "__main__":
    print("Starting mock Ollama on port 11434...")
    uvicorn.run(app, host="0.0.0.0", port=11434)
