import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to generate or extract X-Request-Id header.

    If the client sends an X-Request-Id header, use that.
    Otherwise, generate a new UUID.
    """

    async def dispatch(self, request: Request, call_next):
        # Get request ID from header or generate new one
        request_id = request.headers.get("X-Request-Id")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store request_id in request state for use in endpoints
        request.state.request_id = request_id

        # Call the next middleware/endpoint
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-Id"] = request_id

        return response
