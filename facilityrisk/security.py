"""Fail-closed private auth with optional distinct, role-bound review accounts.

This is *not* production OIDC/SSO or tenant-scoped authorization. Local
research can use a single secret; two-person decisions are only available
after enabling independent Basic accounts with PBKDF2 password verifiers.
Never treat a shared bearer token or a supplied reviewer string as an
independent human identity.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from fastapi import Request
from fastapi.responses import JSONResponse

VALID_ROLES={'viewer','researcher','reviewer','approver','admin'}
ACTOR_RE=re.compile(r'^[a-zA-Z0-9._-]{3,64}$')
MIN_PBKDF2_ITERATIONS=200_000

def dual_review_enabled():
    return os.environ.get('FACILITY_RISK_DUAL_REVIEW')=='1'

def secret_configured():
    return bool(os.environ.get('FACILITY_RISK_AUTH_TOKEN','') or
                os.environ.get('FACILITY_RISK_USERS_JSON',''))

def make_password_hash(password,*,salt=None,iterations=260_000):
    """Generate verifier for managed environment configuration, never a token."""
    if not isinstance(password,str) or len(password)<16:
        raise ValueError('Use a unique password of at least 16 characters')
    if iterations<MIN_PBKDF2_ITERATIONS:
        raise ValueError('Insufficient PBKDF2 work factor')
    salt=salt or secrets.token_bytes(24)
    if not isinstance(salt,bytes) or len(salt)<16:raise ValueError('Salt must be >=16 bytes')
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,iterations)
    return 'pbkdf2_sha256$'+str(iterations)+'$'+salt.hex()+'$'+digest.hex()

def verify_password(password,stored):
    try:
        typ,count,salt,digest=str(stored).split('$')
        count=int(count)
        if typ!='pbkdf2_sha256' or count<MIN_PBKDF2_ITERATIONS or count>1_000_000:
            return False
        salt_bytes=bytes.fromhex(salt);expected=bytes.fromhex(digest)
        if len(salt_bytes)<16 or len(expected)!=32:return False
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),salt_bytes,count)
        return secrets.compare_digest(actual,expected)
    except (ValueError,TypeError,UnicodeEncodeError):
        return False

def configured_users():
    raw=os.environ.get('FACILITY_RISK_USERS_JSON','')
    if not raw:return {}
    try:
        users=json.loads(raw)
        if not isinstance(users,dict) or not users:raise ValueError('No accounts')
        result={}
        for username,config in users.items():
            if not isinstance(username,str) or not ACTOR_RE.fullmatch(username):
                raise ValueError('Invalid username')
            if not isinstance(config,dict) or config.get('role') not in VALID_ROLES:
                raise ValueError('Invalid role')
            verifier=config.get('password_hash')
            if not isinstance(verifier,str) or not verifier.startswith('pbkdf2_sha256$'):
                raise ValueError('Missing password verifier')
            result[username]={'role':config['role'],'password_hash':verifier}
        return result
    except (ValueError,TypeError,json.JSONDecodeError) as e:
        raise RuntimeError('FACILITY_RISK_USERS_JSON is invalid; refusing protected access') from e

def authenticate_context(request:Request):
    users=configured_users()
    expected=os.environ.get('FACILITY_RISK_AUTH_TOKEN','')
    h=request.headers.get('authorization','')
    if h.lower().startswith('basic '):
        try:
            decoded=base64.b64decode(h[6:],validate=True).decode('utf-8')
            username,password=decoded.split(':',1)
            if users:
                info=users.get(username)
                if info and verify_password(password,info['password_hash']):
                    return username,info['role']
                return None
            if len(expected)>=24:
                user=os.environ.get('FACILITY_RISK_BASIC_USER','analyst')
                if (secrets.compare_digest(username,user) and
                    secrets.compare_digest(password,expected)):
                    return username,'legacy_shared_secret'
        except (ValueError,UnicodeDecodeError):
            return None
    if h.lower().startswith('bearer ') and len(expected)>=24:
        if secrets.compare_digest(h[7:],expected):
            return 'service-account','service'
        return None
    if users or os.environ.get('FACILITY_RISK_REQUIRE_AUTH')=='1' or expected:
        return None
    remote=request.client.host if request.client else ''
    if remote in ('127.0.0.1','::1','localhost','testclient'):
        return 'local-development','local_development'
    return None

def authenticate(request:Request):
    """Legacy actor-only API; role is always determined by verified credentials."""
    result=authenticate_context(request)
    return result[0] if result else None

def require_review_role(request:Request,role):
    """Role-bound decision gate, active only when independent review is on."""
    if not dual_review_enabled():return
    assigned=getattr(request.state,'role','')
    allowed={'reviewer':{'reviewer','admin'},
             'approver':{'approver','admin'}}
    if assigned not in allowed[role]:
        raise PermissionError('An independently authenticated '+role+' account is required')

def add_security(app):
    @app.middleware('http')
    async def auth(request:Request,call_next):
        if request.url.path in ('/api/health','/healthz'):
            return await call_next(request)
        try:context=authenticate_context(request)
        except RuntimeError:
            return JSONResponse(status_code=503,content={'detail':'Authentication configuration invalid'},
                                headers={'Cache-Control':'no-store'})
        if context is None:
            return JSONResponse(status_code=401,content={'detail':'Authentication required'},
                     headers={'WWW-Authenticate':'Basic realm="Facility Risk Private"',
                              'Cache-Control':'no-store'})
        request.state.actor,request.state.role=context
        if dual_review_enabled() and request.method in ('POST','PUT','PATCH','DELETE'):
            role=request.state.role
            if role not in ('researcher','reviewer','approver','admin'):
                return JSONResponse(status_code=403,content={'detail':'Personal authorized write role required'},
                                    headers={'Cache-Control':'no-store'})
            if role=='approver' and not request.url.path.startswith('/api/review-approvals/'):
                return JSONResponse(status_code=403,content={'detail':'Approval role cannot perform researcher writes'},
                                    headers={'Cache-Control':'no-store'})
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api') else 'max-age=300'
        return response

def validate_private_bind(host:str):
    if host not in ('127.0.0.1','localhost','::1') and not secret_configured():
        raise RuntimeError('Refusing non-loopback binding without independent credentials')
    token=os.environ.get('FACILITY_RISK_AUTH_TOKEN','')
    if token and len(token)<24:
        raise RuntimeError('FACILITY_RISK_AUTH_TOKEN must have at least 24 characters')
    accounts=configured_users()
    if dual_review_enabled():
        if not accounts:
            raise RuntimeError('Independent review requires individually authenticated user accounts')
        roles={v['role'] for v in accounts.values()}
        if not roles.intersection({'reviewer','admin'}) or not roles.intersection({'approver','admin'}):
            raise RuntimeError('Independent review needs reviewer and approver credentials')
        if len(accounts)<2:
            raise RuntimeError('Two-person approval requires distinct user identities')
    if (host not in ('127.0.0.1','localhost','::1') and
        os.environ.get('FACILITY_RISK_ENABLE_WRITES')=='1' and
        not dual_review_enabled()):
        raise RuntimeError('Non-loopback writes require independent review enforcement')
