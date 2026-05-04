import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_SKIP_PATHS = {"/health", "/debug"}


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
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
            email = payload.get("email") or payload.get("sub", "")
            if not email:
                logger.warning("JWT payload missing email/sub: %s", list(payload.keys()))
                return JSONResponse(status_code=401, content={"detail": "Token missing email claim"})
            request.state.user_email = email
        except JWTError as exc:
            logger.warning("JWT validation failed: %s", exc)
            return JSONResponse(status_code=401, content={"detail": f"JWT error: {exc}"})

        return await call_next(request)
