from datetime import datetime, timedelta, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import requests
from core.database import SessionLocal
from crud.user_crud import get_user_by_email, create_user
from crud.session_crud import create_session
from schemas.session_schema import SessionCreate
from schemas.user_schema import UserCreate, UserResponse
from schemas.auth_schema import GoogleLoginRequest, AuthTokenResponse, LoginUrlResponse
from core.config import settings
from core.auth import get_current_user
from crud.verification_crud import create_verification, get_by_identifier_value, delete_verification
from schemas.verification_schema import VerificationCreate
import urllib.parse

router = APIRouter(prefix="/auth", tags=["Authentication"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/google", response_model=UserResponse)
def google_auth(token: dict, db: Session = Depends(get_db)):
    """
    Accepts Google ID token and returns authenticated user.
    """
    id_token = token.get("token")
    if not id_token:
        raise HTTPException(status_code=400, detail="Missing token")

    response = requests.get(
        f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
    )
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Invalid token")

    payload = response.json()
    email = payload.get("email")
    name = payload.get("name")
    image = payload.get("picture")

    user = get_user_by_email(db, email)
    if not user:
        user = create_user(db, UserCreate(email=email, name=name, image=image))
    return user


@router.post("/login/google", response_model=AuthTokenResponse)
def google_login(body: GoogleLoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Verify Google ID token, upsert user, and issue a bearer token.
    """
    id_token = body.token
    response = requests.get(
        f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
    )
    if response.status_code != 200:
        raise HTTPException(status_code=400, detail="Invalid token")

    payload = response.json()
    email = payload.get("email")
    name = payload.get("name")
    image = payload.get("picture")
    if not email:
        raise HTTPException(status_code=400, detail="Token missing email")

    user = get_user_by_email(db, email)
    if not user:
        user = create_user(db, UserCreate(email=email, name=name, image=image))

    # Issue session token
    token = uuid.uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    session = create_session(
        db,
        payload=SessionCreate(
            user_id=user.id,
            token=token,
            expires_at=expires_at,
            ip_address=ip,
            user_agent=ua,
        ),
    )

    return AuthTokenResponse(access_token=session.token, user=user)


@router.get("/me", response_model=UserResponse)
def get_me(current_user = Depends(get_current_user)):
    return current_user


@router.get("/google/login", response_model=LoginUrlResponse)
def google_login_url(request: Request, db: Session = Depends(get_db)):
    """
    Create a state token and return the Google OAuth consent URL.
    """
    state = uuid.uuid4().hex
    # State expires in 10 minutes
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    create_verification(db, VerificationCreate(identifier="oauth_state", value=state, expires_at=expires_at))

    # Build redirect_uri dynamically from the current request host/port
    redirect_uri = str(request.url_for("google_callback"))
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "state": state,
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return LoginUrlResponse(url=url)


@router.get("/google/callback")
def google_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)):
    """
    Handle Google OAuth callback, exchange code for tokens, upsert user, create session,
    and redirect to FRONTEND_URL with the session token.
    """
    # Validate state
    ver = get_by_identifier_value(db, identifier="oauth_state", value=state)
    if not ver:
        raise HTTPException(status_code=400, detail="Invalid state")
    expires_at = ver.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid state")

    # One-time use
    delete_verification(db, ver.id)

    # Must match the redirect_uri used in the initial authorization request
    redirect_uri = str(request.url_for("google_callback"))
    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Token exchange failed")

    tokens = token_resp.json()
    access_token = tokens.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token returned")

    userinfo = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if userinfo.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch userinfo")

    info = userinfo.json()
    email = info.get("email")
    name = info.get("name")
    image = info.get("picture")
    if not email:
        raise HTTPException(status_code=400, detail="No email in userinfo")

    user = get_user_by_email(db, email)
    if not user:
        user = create_user(db, UserCreate(email=email, name=name, image=image))

    # Issue session token
    token = uuid.uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    session = create_session(
        db,
        payload=SessionCreate(
            user_id=user.id,
            token=token,
            expires_at=expires_at,
            ip_address=ip,
            user_agent=ua,
        ),
    )

    # Redirect to frontend with token
    fe = settings.FRONTEND_URL.rstrip('/')
    redirect_to = f"{fe}/auth/callback?token={urllib.parse.quote(session.token)}"
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=redirect_to, status_code=302)
