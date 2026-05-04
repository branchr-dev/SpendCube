import logging
import os

import jwt as pyjwt
from jwt import PyJWKClient
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_SKIP_PATHS = {"/health", "/debug"}
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    if _jwks_client is None:
        supabase_url = os.getenv("SUPABASE_URL", "")
        if supabase_url:
            _jwks_client = PyJWKClient(
                f"{supabase_url}/auth/v1/.well-known/jwks.json",
                cache_keys=True,
                lifespan=3600,
            )
    return _jwks_client


class SupabaseAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid Authorization header"})

        token = auth_header[len("Bearer "):]

        try:
            header = pyjwt.get_unverified_header(token)
            token_alg = header.get("alg", "unknown")
        except Exception:
            token_alg = "unreadable"

        try:
            if token_alg in ("HS256", "HS384", "HS512"):
                secret = os.getenv("SUPABASE_JWT_SECRET", "")
                payload = pyjwt.decode(
                    token,
                    secret,
                    algorithms=["HS256", "HS384", "HS512"],
                    options={"verify_aud": False},
                )
            else:
                # ES256 / RS256 — verify via Supabase JWKS endpoint
                client = _get_jwks_client()
                if client is None:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Cannot verify JWT: SUPABASE_URL not configured"},
                    )
                signing_key = client.get_signing_key_from_jwt(token)
                payload = pyjwt.decode(
                    token,
                    signing_key.key,
                    algorithms=[token_alg],
                    options={"verify_aud": False},
                )

            email = payload.get("email") or payload.get("sub", "")
            if not email:
                return JSONResponse(status_code=401, content={"detail": "Token missing email claim"})
            request.state.user_email = email

        except pyjwt.PyJWTError as exc:
            logger.warning("JWT validation failed (alg=%s): %s", token_alg, exc)
            return JSONResponse(status_code=401, content={"detail": f"JWT error (alg={token_alg}): {exc}"})
        except Exception as exc:
            logger.warning("JWT validation error (alg=%s): %s", token_alg, exc)
            return JSONResponse(status_code=401, content={"detail": f"JWT error (alg={token_alg}): {exc}"})

        return await call_next(request)
