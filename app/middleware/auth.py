from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import get_settings
from ..database import get_user_by_api_key

settings = get_settings()
security = HTTPBearer(auto_error=False)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware for API key authentication."""

    # Paths that don't require authentication
    PUBLIC_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for public paths
        if path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Skip auth for admin paths (handled separately)
        if path.startswith("/admin"):
            return await call_next(request)

        # Extract API key from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid Authorization header format. Use 'Bearer <api_key>'"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        api_key = auth_header[7:]  # Remove "Bearer " prefix

        # Validate API key
        user = await get_user_by_api_key(api_key)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid API key"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Store user info in request state for later use
        request.state.user = user

        return await call_next(request)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Dependency to get the current authenticated user."""
    # Check if user was set by middleware
    if hasattr(request.state, "user") and request.state.user:
        return request.state.user

    # Fallback to manual extraction (for routes that might skip middleware)
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_by_api_key(credentials.credentials)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def verify_admin_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> bool:
    """Dependency to verify admin API key."""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != settings.admin_api_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid admin API key",
        )

    return True
