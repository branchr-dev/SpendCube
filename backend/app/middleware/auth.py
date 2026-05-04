import logging
import os

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_SKIP_PATHS = {"/health"}


class SupabaseAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid Authorization header"})

        token = auth_header[len("Bearer "):]
        supabase_url = os.getenv("SUPABASE_URL", "")
        anon_key = os.getenv("SUPABASE_ANON_KEY", "")

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{supabase_url}/auth/v1/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "apikey": anon_key,
                    },
                )
            if resp.status_code != 200:
                logger.warning("Supabase token rejected: %s", resp.text)
                return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

            user_data = resp.json()
            email = user_data.get("email", "")
            if not email:
                return JSONResponse(status_code=401, content={"detail": "Token missing email"})

            request.state.user_email = email

        except httpx.TimeoutException:
            logger.error("Supabase auth check timed out")
            return JSONResponse(status_code=503, content={"detail": "Auth service timeout"})
        except Exception as exc:
            logger.error("Auth check failed: %s", exc)
            return JSONResponse(status_code=401, content={"detail": "Auth check failed"})

        return await call_next(request)
