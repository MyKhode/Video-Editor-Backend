import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Request
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from core.config import settings
from crud.asset_crud import create_asset, find_asset_by_name_project_user, find_asset_by_storage_key, delete_asset
from schemas.asset_schema import AssetResponse, AssetCreate
from pydantic import BaseModel


router = APIRouter(tags=["Upload"])


def _normalize_filename(original_name: str) -> str:
    """Normalize filename without adding randomness.
    - Trim whitespace
    - Replace spaces with underscores
    - Preserve original extension
    """
    name, ext = os.path.splitext(original_name or "file")
    name = name.strip().replace(" ", "_")
    return f"{name}{ext}"


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

    # Use frontend-provided name (normalized), do not append randomness
    original_client_name = media.filename or "file"
    filename = _normalize_filename(original_client_name)
    file_path = os.path.join(settings.MEDIA_DIR, filename)

    # Duplicate check: if same storage_key exists for this user (any project) or on disk
    try:
        existing = find_asset_by_storage_key(db, current_user.id, None, filename)
    except Exception:
        existing = None
    if existing is not None or os.path.exists(file_path):
        raise HTTPException(status_code=409, detail="Duplicate media")

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


class MediaSplitRequest(BaseModel):
    # Identify source either by storage_key or name
    storage_key: Optional[str] = None
    name: Optional[str] = None
    project_id: Optional[str] = None
    split_time: float  # seconds, must be within (0, duration)
    keep_original: bool = False


@router.post("/media/split")
def split_media(
    request: Request,
    body: MediaSplitRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Split an audio/video asset into two files at split_time (seconds).
    Creates two new assets, optionally deletes original. Returns new asset URLs.
    """
    # Locate asset
    asset = None
    if body.storage_key:
        asset = find_asset_by_storage_key(db, current_user.id, body.project_id, body.storage_key)
    if not asset and body.name:
        asset = find_asset_by_name_project_user(db, current_user.id, body.project_id, body.name)
    if not asset:
        raise HTTPException(status_code=404, detail="Source media not found")

    src_path = os.path.join(settings.MEDIA_DIR, asset.storage_key)
    if not os.path.exists(src_path):
        raise HTTPException(status_code=404, detail="Source file missing on server")

    # Determine media type
    mime = asset.mime_type or ""
    is_video = mime.startswith("video/") or asset.storage_key.lower().endswith((".mp4", ".mov", ".mkv", ".webm"))
    is_audio = mime.startswith("audio/") or asset.storage_key.lower().endswith((".mp3", ".wav", ".aac", ".m4a", ".ogg"))
    if not (is_video or is_audio):
        raise HTTPException(status_code=400, detail="Only audio/video splitting is supported")

    split_t = float(body.split_time)
    if split_t <= 0:
        raise HTTPException(status_code=400, detail="split_time must be > 0")

    # Prepare output filenames
    base, ext = os.path.splitext(asset.storage_key)
    # Normalize output extension
    if is_video and ext.lower() not in (".mp4",):
        ext = ".mp4"
    ts = int(time.time() * 1000)
    out1_name = f"{base}_part1_{ts}{ext}"
    out2_name = f"{base}_part2_{ts}{ext}"
    out1_path = os.path.join(settings.MEDIA_DIR, out1_name)
    out2_path = os.path.join(settings.MEDIA_DIR, out2_name)

    dur1 = 0.0
    dur2 = 0.0
    width = None
    height = None

    try:
        if is_video:
            try:
                from moviepy import VideoFileClip
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"moviepy not available: {e}")
            clip = VideoFileClip(src_path)
            total = float(getattr(clip, "duration", 0.0) or 0.0)
            if split_t >= total:
                clip.close()
                raise HTTPException(status_code=400, detail="split_time beyond duration")
            w, h = getattr(clip, "size", (None, None)) or (None, None)
            width, height = w, h
            # Safe subclip across MoviePy versions
            if hasattr(clip, "subclip"):
                c1 = clip.subclip(0, split_t)
                c2 = clip.subclip(split_t, total)
            else:
                c1 = clip.subclipped(0, split_t)
                c2 = clip.subclipped(split_t, total)
            dur1 = float(getattr(c1, "duration", split_t))
            dur2 = float(getattr(c2, "duration", max(0.0, total - split_t)))
            # Write outputs
            try:
                c1.write_videofile(out1_path, codec="libx264", audio_codec="aac")
            except TypeError:
                c1.write_videofile(out1_path)
            try:
                c2.write_videofile(out2_path, codec="libx264", audio_codec="aac")
            except TypeError:
                c2.write_videofile(out2_path)
            c1.close(); c2.close(); clip.close()
        else:
            try:
                from moviepy import AudioFileClip
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"moviepy not available: {e}")
            a = AudioFileClip(src_path)
            total = float(getattr(a, "duration", 0.0) or 0.0)
            if split_t >= total:
                a.close()
                raise HTTPException(status_code=400, detail="split_time beyond duration")
            if hasattr(a, "subclip"):
                a1 = a.subclip(0, split_t)
                a2 = a.subclip(split_t, total)
            else:
                a1 = a.subclipped(0, split_t)
                a2 = a.subclipped(split_t, total)
            dur1 = float(getattr(a1, "duration", split_t))
            dur2 = float(getattr(a2, "duration", max(0.0, total - split_t)))
            # Choose codec based on ext
            ext_lower = ext.lower()
            if ext_lower in (".mp3",):
                codec = "libmp3lame"
            elif ext_lower in (".wav",):
                codec = "pcm_s16le"
            else:
                codec = None
            if codec:
                a1.write_audiofile(out1_path, codec=codec)
                a2.write_audiofile(out2_path, codec=codec)
            else:
                a1.write_audiofile(out1_path)
                a2.write_audiofile(out2_path)
            a1.close(); a2.close(); a.close()
    except HTTPException:
        raise
    except Exception as e:
        # Cleanup partial files
        for p in (out1_path, out2_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Split failed: {e}")

    # Persist assets
    def _guess_mime(filename: str) -> str:
        import mimetypes
        return mimetypes.guess_type(filename)[0] or ("video/mp4" if filename.endswith(".mp4") else "application/octet-stream")

    url_base = str(request.base_url).rstrip("/") + settings.MEDIA_URL_PATH + "/"
    out1_size = os.path.getsize(out1_path) if os.path.exists(out1_path) else 0
    out2_size = os.path.getsize(out2_path) if os.path.exists(out2_path) else 0

    asset1 = create_asset(
        db,
        AssetCreate(
            user_id=current_user.id,
            project_id=asset.project_id,
            original_name=os.path.basename(out1_name),
            storage_key=out1_name,
            mime_type=_guess_mime(out1_name),
            size_bytes=out1_size,
            width=width if is_video else None,
            height=height if is_video else None,
            duration_seconds=dur1,
        ),
    )
    asset2 = create_asset(
        db,
        AssetCreate(
            user_id=current_user.id,
            project_id=asset.project_id,
            original_name=os.path.basename(out2_name),
            storage_key=out2_name,
            mime_type=_guess_mime(out2_name),
            size_bytes=out2_size,
            width=width if is_video else None,
            height=height if is_video else None,
            duration_seconds=dur2,
        ),
    )

    # Optionally delete original
    if not body.keep_original:
        try:
            file_path = os.path.join(settings.MEDIA_DIR, asset.storage_key)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
        delete_asset(db, asset.id)

    return {
        "left": {
            "url": url_base + out1_name,
            "asset": AssetResponse.model_validate(asset1),
        },
        "right": {
            "url": url_base + out2_name,
            "asset": AssetResponse.model_validate(asset2),
        },
    }


class MediaSplitByIdRequest(BaseModel):
    asset_id: str
    project_id: Optional[str] = None
    # Either provide split_time in seconds or split_frames + fps
    split_time: Optional[float] = None
    split_frames: Optional[int] = None
    fps: int = 30
    keep_original: bool = False


@router.post("/media/split-by-id")
def split_media_by_id(
    request: Request,
    body: MediaSplitByIdRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    from crud.asset_crud import get_asset

    asset = get_asset(db, body.asset_id)
    if not asset or asset.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Ensure project association
    target_project_id = body.project_id or asset.project_id

    # Compute split time: prefer frames-based to match editor trim frames
    split_t = None
    if body.split_frames is not None and body.fps and body.fps > 0:
        split_t = float(body.split_frames) / float(body.fps)
    elif body.split_time is not None:
        split_t = float(body.split_time)
    else:
        raise HTTPException(status_code=400, detail="Provide split_time or split_frames+fps")

    # Reuse splitting logic by adapting locals, without mutating original object
    class _TmpReq(BaseModel):
        storage_key: Optional[str] = None
        name: Optional[str] = None
        project_id: Optional[str] = None
        split_time: float
        keep_original: bool = False

    tmp_req = _TmpReq(storage_key=asset.storage_key, name=None, project_id=target_project_id, split_time=split_t, keep_original=body.keep_original)

    # Inline call to the same core implemented above (duplicated minimal to avoid refactor)
    src_path = os.path.join(settings.MEDIA_DIR, asset.storage_key)
    if not os.path.exists(src_path):
        raise HTTPException(status_code=404, detail="Source file missing on server")

    mime = asset.mime_type or ""
    is_video = mime.startswith("video/") or asset.storage_key.lower().endswith((".mp4", ".mov", ".mkv", ".webm"))
    is_audio = mime.startswith("audio/") or asset.storage_key.lower().endswith((".mp3", ".wav", ".aac", ".m4a", ".ogg"))
    if not (is_video or is_audio):
        raise HTTPException(status_code=400, detail="Only audio/video splitting is supported")

    split_t = float(tmp_req.split_time)
    if split_t <= 0:
        # minimal positive duration to avoid zero-length part
        split_t = 0.033

    base, ext = os.path.splitext(asset.storage_key)
    if is_video and ext.lower() not in (".mp4",):
        ext = ".mp4"
    ts = int(time.time() * 1000)
    out1_name = f"{base}_part1_{ts}{ext}"
    out2_name = f"{base}_part2_{ts}{ext}"
    out1_path = os.path.join(settings.MEDIA_DIR, out1_name)
    out2_path = os.path.join(settings.MEDIA_DIR, out2_name)

    dur1 = 0.0
    dur2 = 0.0
    width = None
    height = None

    try:
        if is_video:
            try:
                from moviepy import VideoFileClip
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"moviepy not available: {e}")
            clip = VideoFileClip(src_path)
            total = float(getattr(clip, "duration", 0.0) or 0.0)
            if split_t >= total:
                # Clamp split to just before end to ensure two non-empty parts
                split_t = max(0.0, total - 0.033)
            w, h = getattr(clip, "size", (None, None)) or (None, None)
            width, height = w, h
            if hasattr(clip, "subclip"):
                c1 = clip.subclip(0, split_t)
                c2 = clip.subclip(split_t, total)
            else:
                c1 = clip.subclipped(0, split_t)
                c2 = clip.subclipped(split_t, total)
            dur1 = float(getattr(c1, "duration", split_t))
            dur2 = float(getattr(c2, "duration", max(0.0, total - split_t)))
            try:
                c1.write_videofile(out1_path, codec="libx264", audio_codec="aac")
            except TypeError:
                c1.write_videofile(out1_path)
            try:
                c2.write_videofile(out2_path, codec="libx264", audio_codec="aac")
            except TypeError:
                c2.write_videofile(out2_path)
            c1.close(); c2.close(); clip.close()
        else:
            try:
                from moviepy import AudioFileClip
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"moviepy not available: {e}")
            a = AudioFileClip(src_path)
            total = float(getattr(a, "duration", 0.0) or 0.0)
            if split_t >= total:
                split_t = max(0.0, total - 0.033)
            if hasattr(a, "subclip"):
                a1 = a.subclip(0, split_t)
                a2 = a.subclip(split_t, total)
            else:
                a1 = a.subclipped(0, split_t)
                a2 = a.subclipped(split_t, total)
            dur1 = float(getattr(a1, "duration", split_t))
            dur2 = float(getattr(a2, "duration", max(0.0, total - split_t)))
            ext_lower = ext.lower()
            if ext_lower in (".mp3",):
                codec = "libmp3lame"
            elif ext_lower in (".wav",):
                codec = "pcm_s16le"
            else:
                codec = None
            if codec:
                a1.write_audiofile(out1_path, codec=codec)
                a2.write_audiofile(out2_path, codec=codec)
            else:
                a1.write_audiofile(out1_path)
                a2.write_audiofile(out2_path)
            a1.close(); a2.close(); a.close()
    except HTTPException:
        raise
    except Exception as e:
        for p in (out1_path, out2_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Split failed: {e}")

    import mimetypes
    def _guess_mime(filename: str) -> str:
        return mimetypes.guess_type(filename)[0] or ("video/mp4" if filename.endswith(".mp4") else "application/octet-stream")

    url_base = str(request.base_url).rstrip("/") + settings.MEDIA_URL_PATH + "/"
    out1_size = os.path.getsize(out1_path) if os.path.exists(out1_path) else 0
    out2_size = os.path.getsize(out2_path) if os.path.exists(out2_path) else 0

    asset1 = create_asset(
        db,
        AssetCreate(
            user_id=current_user.id,
            project_id=target_project_id,
            original_name=os.path.basename(out1_name),
            storage_key=out1_name,
            mime_type=_guess_mime(out1_name),
            size_bytes=out1_size,
            width=width if is_video else None,
            height=height if is_video else None,
            duration_seconds=dur1,
        ),
    )
    asset2 = create_asset(
        db,
        AssetCreate(
            user_id=current_user.id,
            project_id=target_project_id,
            original_name=os.path.basename(out2_name),
            storage_key=out2_name,
            mime_type=_guess_mime(out2_name),
            size_bytes=out2_size,
            width=width if is_video else None,
            height=height if is_video else None,
            duration_seconds=dur2,
        ),
    )

    if not body.keep_original:
        try:
            file_path = os.path.join(settings.MEDIA_DIR, asset.storage_key)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
        delete_asset(db, asset.id)

    return {
        "ok": True,
        "left": {"url": url_base + out1_name, "asset": AssetResponse.model_validate(asset1)},
        "right": {"url": url_base + out2_name, "asset": AssetResponse.model_validate(asset2)},
    }
