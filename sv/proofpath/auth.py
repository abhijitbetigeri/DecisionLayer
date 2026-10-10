"""Local-demo access boundary (README: not production authentication).

- Every browser/agent gets an opaque session cookie; evaluations belong to the session that made them.
- Operator actions need PROOFPATH_OPERATOR_TOKEN, checked server-side only. Operators log in once via
  POST /operator/login (form or JSON {token}); the token itself is never sent to page JavaScript.
"""
from __future__ import annotations

import hmac
import os
import secrets

from fastapi import HTTPException, Request

SESSION_COOKIE = "dl_session"
OPERATOR_COOKIE = "dl_operator"
_operator_sessions: set[str] = set()


def operator_token() -> str | None:
    return os.environ.get("PROOFPATH_OPERATOR_TOKEN") or None


def session_id(request: Request) -> str:
    sid = request.cookies.get(SESSION_COOKIE) or getattr(request.state, "new_session", None)
    if not sid:
        raise HTTPException(401, "no session")
    return sid


def new_session_id() -> str:
    return secrets.token_urlsafe(24)


def check_token(candidate: str | None) -> bool:
    expected = operator_token()
    return bool(expected and candidate and hmac.compare_digest(candidate, expected))


def grant_operator() -> str:
    sid = secrets.token_urlsafe(24)
    _operator_sessions.add(sid)
    return sid


def is_operator(request: Request) -> bool:
    if check_token(request.headers.get("x-operator-token")):
        return True
    return request.cookies.get(OPERATOR_COOKIE) in _operator_sessions


def require_operator(request: Request) -> None:
    if not is_operator(request):
        raise HTTPException(403, "operator authorization required")
