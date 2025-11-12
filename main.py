from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.staticfiles import StaticFiles
from core.database import Base, engine
from routers import user_router
from routers import auth_router
from routers import project_router, asset_router, session_router, account_router, verification_router
from routers import upload_router
from routers import render_router
from models import user, session, account, verification, project, asset
from core.config import settings

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Video Editor Backend API")

# Respect X-Forwarded-Proto/Host when behind a proxy (Docker/nginx/etc.)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# CORS: allow all domains and headers/methods
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(user_router.router)
app.include_router(auth_router.router)
app.include_router(project_router.router)
app.include_router(asset_router.router)
app.include_router(session_router.router)
app.include_router(account_router.router)
app.include_router(verification_router.router)
app.include_router(upload_router.router)
app.include_router(render_router.router)

# Static media mount
import os as _os
_os.makedirs(settings.MEDIA_DIR, exist_ok=True)
app.mount(
    settings.MEDIA_URL_PATH,
    StaticFiles(directory=settings.MEDIA_DIR),
    name="media",
)

@app.get("/")
def root():
    return {"message": "🎬 Video Editor Backend API Ready"}
