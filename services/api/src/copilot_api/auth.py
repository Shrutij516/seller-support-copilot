"""Bearer JWT authentication and role-based authorization.

Verification happens in the API itself (not an API Gateway authorizer): RS256 signature via
JWKS, `iss` matches the configured Cognito issuer, `exp` (checked by PyJWT by default),
`token_use == "access"` (rejects ID tokens), and `client_id` matches the configured app
client. Roles come from the `cognito:groups` claim. A seller's identity is resolved by
looking up `sellers.cognito_sub == sub`; a principal with no matching row has no
`seller_id` and can't access any seller-owned resource.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from copilot_api.config import Settings, get_settings
from copilot_api.deps import get_db_session
from copilot_api.errors import ProblemError, forbidden, unauthorized
from copilot_api.models import Seller


class TokenError(Exception):
    """Any reason a bearer token fails verification; callers map this to 401."""


class UnknownKeyIdError(TokenError):
    def __init__(self, kid: str) -> None:
        super().__init__(f"no signing key for kid {kid!r}")
        self.kid = kid


class JWKSCache:
    """Caches JWKS signing keys by `kid`; refetches (once) only when an unknown `kid` shows
    up, never on a timer. A stale cache just means a key rotation triggers one extra fetch
    the next time a token signed with the new key arrives.
    """

    def __init__(self, jwks_url: str) -> None:
        self._jwks_url = jwks_url
        self._client = httpx.AsyncClient(timeout=5.0)
        self._keys_by_kid: dict[str, jwt.PyJWK] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    @classmethod
    def for_testing(cls, jwks_document: dict[str, Any]) -> JWKSCache:
        """A cache pre-populated from a JWKS document already in hand: no HTTP, no real
        JWKS URL. `_fetch` becomes a no-op, so a `kid` the document doesn't have behaves
        exactly like a real "refetched and still unknown" key: UnknownKeyIdError, not a
        network call to nowhere.
        """
        instance = cls(jwks_url="")
        jwk_set = jwt.PyJWKSet.from_dict(jwks_document)
        instance._keys_by_kid = {key.key_id: key for key in jwk_set.keys if key.key_id}

        async def _no_refetch() -> None:
            return None

        instance._fetch = _no_refetch  # type: ignore[method-assign]
        return instance

    async def _fetch(self) -> None:
        response = await self._client.get(self._jwks_url)
        response.raise_for_status()
        jwk_set = jwt.PyJWKSet.from_dict(response.json())
        self._keys_by_kid = {key.key_id: key for key in jwk_set.keys if key.key_id}

    async def get_signing_key(self, kid: str) -> jwt.PyJWK:
        if kid not in self._keys_by_kid:
            await self._fetch()
        try:
            return self._keys_by_kid[kid]
        except KeyError:
            raise UnknownKeyIdError(kid) from None


async def verify_access_token(token: str, jwks: JWKSCache, settings: Settings) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise TokenError("malformed token header") from exc

    kid = header.get("kid")
    if not kid:
        raise TokenError("token header missing kid")

    signing_key = await jwks.get_signing_key(kid)

    try:
        claims = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256"],
            issuer=settings.cognito_issuer,
            options={"require": ["exp", "iss", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

    if claims.get("token_use") != "access":
        raise TokenError("not an access token")
    if claims.get("client_id") != settings.cognito_app_client_id:
        raise TokenError("token was not issued for this app client")

    return claims


def get_jwks_cache(request: Request) -> JWKSCache:
    cache: JWKSCache = request.app.state.jwks_cache
    return cache


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise TokenError("missing bearer token")
    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise TokenError("missing bearer token")
    return token


@dataclass(frozen=True, slots=True)
class Principal:
    sub: str
    roles: frozenset[str]
    seller_id: uuid.UUID | None


async def get_current_principal(
    request: Request,
    settings: Settings = Depends(get_settings),
    jwks: JWKSCache = Depends(get_jwks_cache),
    session: AsyncSession = Depends(get_db_session),
) -> Principal:
    try:
        token = _bearer_token(request)
        claims = await verify_access_token(token, jwks, settings)
    except TokenError as exc:
        raise unauthorized(str(exc)) from exc

    sub = str(claims["sub"])
    roles = frozenset(claims.get("cognito:groups") or [])
    seller = (
        await session.execute(select(Seller).where(Seller.cognito_sub == sub))
    ).scalar_one_or_none()
    return Principal(sub=sub, roles=roles, seller_id=seller.id if seller else None)


def require_role(*roles: str) -> Callable[..., Any]:
    """FastAPI dependency factory: 403 if the caller's cognito:groups don't intersect
    `roles`. Route handlers depend on this, not on checking roles themselves.
    """
    allowed = frozenset(roles)

    async def _require_role(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if not (principal.roles & allowed):
            raise forbidden("this route requires a role you don't have")
        return principal

    return _require_role


def require_seller(principal: Principal = Depends(require_role("seller"))) -> uuid.UUID:
    """A seller-role principal resolved to their own seller_id. Raises the same 403 as
    require_role if the caller isn't a seller; raises 404-shaped ProblemError if they're in
    the seller group but have no matching sellers row (misconfigured account, not a
    cross-tenant probe, but still nothing for them to see).
    """
    if principal.seller_id is None:
        raise ProblemError(404, "Not Found", "no seller account for this user")
    return principal.seller_id
