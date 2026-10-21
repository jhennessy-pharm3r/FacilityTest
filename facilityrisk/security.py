"""Fail-closed single-tenant auth for private API prototype.

This is NOT full insurer RBAC/SSO. It supplies an HTTPS reverse-proxy-compatible
basic-auth challenge and bearer token for machine imports. Deploy only over TLS.
"""
from __future__ import annotations
import base64
import os
import secrets
from fastapi import Request
from fastapi.responses import JSONResponse


def secret_configured():return bool(os.environ.get('FACILITY_RISK_AUTH_TOKEN',''))


def authenticate(request: Request) -> str | None:
    expected=os.environ.get('FACILITY_RISK_AUTH_TOKEN','')
    if not expected:
        if os.environ.get('FACILITY_RISK_REQUIRE_AUTH')=='1': return None
        # A direct external ASGI launch must not bypass CLI bind protection.
        remote=(request.client.host if request.client else '')
        if remote not in ('127.0.0.1','::1','localhost','testclient'): return None
        return 'local-development'
    if len(expected)<24: return None
    h=request.headers.get('authorization','')
    if h.lower().startswith('bearer '):
        value=h[7:]
        return 'service-account' if secrets.compare_digest(value,expected) else None
    if h.lower().startswith('basic '):
        try:
            user,passwd=base64.b64decode(h[6:],validate=True).decode().split(':',1)
            allowed_user=os.environ.get('FACILITY_RISK_BASIC_USER','analyst')
            if secrets.compare_digest(user,allowed_user) and secrets.compare_digest(passwd,expected):return user
        except (ValueError,UnicodeDecodeError):pass
    return None


def add_security(app):
    @app.middleware('http')
    async def auth(request:Request,call_next):
        if request.url.path in ('/api/health','/healthz'):
            return await call_next(request)
        # In public-mode (no token) runtime must bind loopback; cli enforces.
        actor=authenticate(request)
        if actor is None:
            return JSONResponse(status_code=401,content={'detail':'Authentication required'},
                     headers={'WWW-Authenticate':'Basic realm="Facility Risk Private"',
                              'Cache-Control':'no-store'})
        request.state.actor=actor
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api') else 'max-age=300'
        return response


def validate_private_bind(host:str):
    if host not in ('127.0.0.1','localhost','::1') and not secret_configured():
        raise RuntimeError('Refusing non-loopback binding without FACILITY_RISK_AUTH_TOKEN')
    if secret_configured() and len(os.environ['FACILITY_RISK_AUTH_TOKEN'])<24:
        raise RuntimeError('FACILITY_RISK_AUTH_TOKEN must have at least 24 characters')
