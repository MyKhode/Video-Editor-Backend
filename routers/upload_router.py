import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Request
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from core.config import settings
from crud.asset_crud import create_asset, find_asset_by_name_project_user, delete_asset
from schemas.asset_schema import AssetResponse, AssetCreate
from pydantic import BaseModel


router = APIRouter(tags=["Upload"])


def _safe_filename(original_name: str) -> str:
    name, ext = os.path.splitext(original_name)
    # Normalize name
    name = name.strip().replace(" ", "_")
    if not ext:
        ext = ""
    # Add timestamp to avoid collisions
    ts = int(time.time() * 1000)
    return f"{name}_{ts}{ext}"


@router.post("/upload")
def upload_media(
    request: Request,
    media: UploadFile = File(...),
    project_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    # Ensure media directory exists
    os.makedirs(settings.MEDIA_DIR, exist_ok=True)

    filename = _safe_filename(media.filename or "file")
    file_path = os.path.join(settings.MEDIA_DIR, filename)

    # Stream to disk to avoid high memory usage
    size_bytes = 0
    with open(file_path, "wb") as out:
        while True:
            chunk = media.file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            size_bytes += len(chunk)

    mime = media.content_type or "application/octet-stream"
    width = None
    height = None

    # Image compression (keep same format)
    try:
        if mime.startswith("image/"):
            # Lazy import Pillow to avoid hard dependency at startup
            try:
                from PIL import Image  # type: ignore
            except Exception:
                Image = None  # type: ignore

            if Image is not None:
                with Image.open(file_path) as img:
                    width, height = img.size
                    ext = os.path.splitext(filename)[1].lower()
                    tmp_path = file_path + ".tmp"
                    save_kwargs = {}
                    if ext in (".jpg", ".jpeg"):
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        save_kwargs = {"format": "JPEG", "quality": 85, "optimize": True, "progressive": True}
                    elif ext == ".png":
                        # Preserve PNG but try strongest compression
                        save_kwargs = {"format": "PNG", "optimize": True, "compress_level": 9}
                    elif ext == ".webp":
                        save_kwargs = {"format": "WEBP", "quality": 85, "method": 6}
                    else:
                        save_kwargs = {"format": img.format or None}

                    if save_kwargs.get("format"):
                        img.save(tmp_path, **save_kwargs)
                        new_size = os.path.getsize(tmp_path)
                        if new_size < size_bytes:
                            os.replace(tmp_path, file_path)
                            size_bytes = new_size
                        else:
                            os.remove(tmp_path)
    except Exception:
        # If compression fails, keep original file
        pass

    # Persist asset record
    payload = AssetCreate(
        user_id=current_user.id,
        project_id=project_id,
        original_name=media.filename or filename,
        storage_key=filename,
        mime_type=mime,
        size_bytes=size_bytes,
        width=width,
        height=height,
    )
    asset = create_asset(db, payload)

    # Build absolute URL for the saved media
    media_url = str(request.base_url).rstrip("/") + settings.MEDIA_URL_PATH + "/" + filename

    return {
        "url": media_url,
        "asset": AssetResponse.model_validate(asset),
    }


class MediaDeleteRequest(BaseModel):
    name: str
    project_id: Optional[str] = None


@router.delete("/media")
def delete_media(
    body: MediaDeleteRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    asset = find_asset_by_name_project_user(db, current_user.id, body.project_id, body.name)
    if not asset:
        raise HTTPException(status_code=404, detail="Media not found")

    # Remove file from disk if exists
    file_path = os.path.join(settings.MEDIA_DIR, asset.storage_key)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        # ignore file system errors, continue deleting DB row
        pass

    delete_asset(db, asset.id)
    return {"deleted": True}
