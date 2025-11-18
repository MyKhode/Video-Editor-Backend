import os
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from models.project import Project
from schemas.project_schema import ProjectCreate, ProjectUpdate
from core.config import settings


def get_project(db: Session, project_id: str):
    return db.query(Project).filter(Project.id == project_id).first()


def list_projects(db: Session, user_id: str | None = None, skip: int = 0, limit: int = 100):
    q = db.query(Project)
    if user_id:
        q = q.filter(Project.user_id == user_id)
    return q.order_by(desc(Project.created_at)).offset(skip).limit(limit).all()


def create_project(db: Session, payload: ProjectCreate, user_id: str):
    proj = Project(user_id=user_id, name=payload.name)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


def update_project(db: Session, project_id: str, payload: ProjectUpdate):
    proj = get_project(db, project_id)
    if not proj:
        return None
    if payload.name is not None:
        proj.name = payload.name
    if payload.timeline is not None:
        proj.timeline = payload.timeline
    if payload.text_bin_items is not None:
        proj.text_bin_items = payload.text_bin_items
    db.commit()
    db.refresh(proj)
    return proj


def delete_project(db: Session, project_id: str) -> bool:
    proj = get_project(db, project_id)
    if not proj:
        return False
    # Attempt to delete media files referenced by this project's timeline
    try:
        media_names: set[str] = set()

        def _maybe_add_from_url(url: str):
            if not isinstance(url, str) or not url:
                return
            # If it's an absolute URL containing our media path, use the basename
            if settings.MEDIA_URL_PATH in url:
                name = os.path.basename(urlparse(url).path)
                if name:
                    media_names.add(name)
                return
            # If it's a plain local name/path, take the basename
            if not url.startswith("http://") and not url.startswith("https://"):
                name = os.path.basename(url)
                if name:
                    media_names.add(name)

        def _collect_from_timeline(obj):
            if obj is None:
                return
            # Common keys where media may be referenced
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("mediaUrlRemote", "mediaUrlLocal", "src", "url"):
                        _maybe_add_from_url(v)
                    elif k == "name":
                        # timeline can store just a local filename
                        if isinstance(v, str):
                            media_names.add(os.path.basename(v))
                    else:
                        _collect_from_timeline(v)
            elif isinstance(obj, list):
                for item in obj:
                    _collect_from_timeline(item)

        _collect_from_timeline(getattr(proj, "timeline", None))

        # Also include any Asset rows still tied to this project (backward compatibility)
        try:
            from models.asset import Asset  # type: ignore
            for a in db.query(Asset).filter(Asset.project_id == project_id).all():
                if getattr(a, "storage_key", None):
                    media_names.add(os.path.basename(a.storage_key))
        except Exception:
            # If Asset model is unavailable or query fails, ignore silently
            pass

        # Delete files from media directory
        for name in media_names:
            try:
                path = os.path.join(settings.MEDIA_DIR, name)
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                # Ignore filesystem errors to avoid blocking DB deletion
                pass
    except Exception:
        # Never block project deletion due to cleanup errors
        pass
    db.delete(proj)
    db.commit()
    return True
