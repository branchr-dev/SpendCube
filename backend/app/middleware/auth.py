import os

from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

_SKIP_PATHS = {"/health"}


class SupabaseAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid Authorization header"})

        token = auth_header[len("Bearer "):]
        secret = os.getenv("SUPABASE_JWT_SECRET", "")

        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            request.state.user_email = payload["email"]
        except (JWTError, KeyError):
            return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

        return await call_next(request)
