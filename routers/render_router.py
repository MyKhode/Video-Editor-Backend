import math
import os
import tempfile
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.database import get_db
from core.auth import get_current_user
import requests


router = APIRouter(prefix="/render", tags=["Render"])


def _compute_timeline_duration_seconds(timeline_tracks: List[Dict[str, Any]], pps: float) -> float:
    max_end = 0.0
    for track in timeline_tracks or []:
        for s in track.get("scrubbers", []) or []:
            # Only consider image/video for duration optimization
            mt = (s.get("mediaType") or "").lower()
            if mt not in ("image", "video"):
                continue
            left = float(s.get("left", 0) or 0)
            width = float(s.get("width", 0) or 0)
            start = left / pps if pps else 0
            dur = width / pps if pps else 0
            max_end = max(max_end, start + dur)
    return max_end or 0.0


def _download_to_temp(url: str, suffix: str = "") -> str:
    r = requests.get(url, stream=True, timeout=30)
    r.raise_for_status()
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="media_")
    with os.fdopen(fd, "wb") as out:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                out.write(chunk)
    return path


def _hex_to_rgb(hex_color: str, default=(255, 255, 255)):
    try:
        h = hex_color.lstrip('#')
        if len(h) == 3:
            h = ''.join([c*2 for c in h])
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return default


@router.post("/render")
def render_video(payload: Dict[str, Any], current_user=Depends(get_current_user)):
    """
    Render a composition to MP4 using the provided payload.
    Expected payload keys: timelineData (list of tracks), compositionWidth, compositionHeight,
    durationInFrames, getPixelsPerSecond.
    Media items should reference absolute URLs via `mediaUrlRemote`.
    """
    try:
        from moviepy import (
            VideoFileClip,
            ImageClip,
            CompositeVideoClip,
            ColorClip,
            CompositeAudioClip,
            AudioFileClip,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"moviepy/ffmpeg not available: {e}")

    # Compatibility helpers across MoviePy v1/v2 method changes
    def _with_duration(clip, duration: float):
        if hasattr(clip, "set_duration"):
            return clip.set_duration(duration)
        if hasattr(clip, "with_duration"):
            return clip.with_duration(duration)
        return clip

    def _with_start(clip, start: float):
        if hasattr(clip, "set_start"):
            return clip.set_start(start)
        if hasattr(clip, "with_start"):
            return clip.with_start(start)
        return clip

    def _with_position(clip, pos):
        if hasattr(clip, "set_position"):
            return clip.set_position(pos)
        if hasattr(clip, "with_position"):
            return clip.with_position(pos)
        return clip

    def _resize(clip, size):
        # Prefer classic resize; otherwise fallback
        if hasattr(clip, "resize"):
            try:
                return clip.resize(newsize=size)
            except TypeError:
                return clip.resize(size)
        if hasattr(clip, "with_size"):
            return clip.with_size(size)
        return clip

    timeline = payload.get("timelineData") or payload.get("timeline") or []
    width = int(payload.get("compositionWidth") or 1920)
    height = int(payload.get("compositionHeight") or 1080)
    # Prefer visualDurationInFrames, fallback to durationInFrames
    frames = int(payload.get("visualDurationInFrames") or payload.get("durationInFrames") or 0)
    pps = float(payload.get("getPixelsPerSecond") or 100.0)

    # Determine duration: use provided frames if present; otherwise compute from timeline (image/video only)
    fps = int(payload.get("fps") or 30)
    fps = max(24, min(60, fps))
    timeline_seconds = 0.0
    if frames > 0:
        total_duration = max(1.0 / fps, frames / fps)
    else:
        timeline_seconds = _compute_timeline_duration_seconds(timeline, pps)
        total_duration = max(1.0 / fps, timeline_seconds or (1.0 * 10 / fps))

    base = _with_duration(ColorClip(size=(width, height), color=(0, 0, 0)), total_duration)

    clips = [base]
    audio_clips = []

    # Tracks layering: assume earlier tracks are underneath; later are on top
    for track in timeline or []:
        for s in track.get("scrubbers", []) or []:
            media_type = (s.get("mediaType") or "").lower()
            url = s.get("mediaUrlRemote")
            if not url:
                continue

            start = float(s.get("startTime") or (float(s.get("left", 0)) / pps if pps else 0))
            dur = float(s.get("duration") or (float(s.get("width", 0)) / pps if pps else 0))
            if dur <= 0:
                continue

            left = int(s.get("left_player", 0) or 0)
            top = int(s.get("top_player", 0) or 0)
            w_px = int(s.get("width_player", 0) or 0)
            h_px = int(s.get("height_player", 0) or 0)
            pos = (left, top)

            try:
                if media_type == "image":
                    # Prefetch to local file to improve stability
                    local_path = _download_to_temp(url, suffix=os.path.splitext(url)[1]) if url.startswith("http") else url
                    # Cap duration to project length
                    end = min(start + dur, total_duration)
                    new_dur = max(0.0, end - start)
                    if new_dur <= 0:
                        continue
                    clip = ImageClip(local_path)
                    clip = _with_duration(clip, new_dur)
                    if w_px and h_px:
                        clip = _resize(clip, (w_px, h_px))
                    clip = _with_start(_with_position(clip, pos), start)
                    clips.append(clip)
                elif media_type == "video":
                    local_path = _download_to_temp(url, suffix=os.path.splitext(url)[1]) if url.startswith("http") else url
                    v = VideoFileClip(local_path)
                    trim_before = s.get("trimBefore")
                    # treat trimBefore ms if large value, else seconds
                    if trim_before:
                        tb = float(trim_before)
                        if tb > 1000:
                            tb = tb / 1000.0
                        max_end = min(total_duration, tb + dur)
                        v = v.subclip(tb, min(max_end, getattr(v, "duration", dur)))
                    else:
                        max_end = min(total_duration - start, dur)
                        v = v.subclip(0, max(0.0, min(max_end, getattr(v, "duration", dur))))
                    if w_px and h_px:
                        v = _resize(v, (w_px, h_px))
                    clip = _with_start(_with_position(v, pos), start)
                    clips.append(clip)
                    if getattr(v, "audio", None) is not None:
                        a = v.audio
                        if hasattr(a, "set_start"):
                            a = a.set_start(start)
                        elif hasattr(a, "with_start"):
                            a = a.with_start(start)
                        audio_clips.append(a)
                elif media_type == "text":
                    # Render text using PIL into an ImageClip
                    t = s.get("text") or {}
                    content = (
                        t.get("textContent")
                        or t.get("content")
                        or t.get("value")
                        or s.get("name")
                        or ""
                    )
                    if not content:
                        continue
                    # Lazy import Pillow
                    try:
                        from PIL import Image as PILImage, ImageDraw, ImageFont
                        import numpy as np
                    except Exception:
                        continue
                    w = w_px if w_px else max(200, int(0.3 * width))
                    h = h_px if h_px else max(50, int(0.1 * height))
                    bg = PILImage.new("RGBA", (w, h), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(bg)
                    font_size = int(t.get("fontSize") or 32)
                    font_family = t.get("fontFamily") or "Arial"
                    # Try to load TTF; fallback to default
                    try:
                        font = ImageFont.truetype(font_family, font_size)
                    except Exception:
                        try:
                            font = ImageFont.truetype("arial.ttf", font_size)
                        except Exception:
                            font = ImageFont.load_default()
                    color = _hex_to_rgb(t.get("color") or "#ffffff")
                    align = (t.get("textAlign") or "left").lower()
                    # Simple multiline handling
                    lines = str(content).split("\n")
                    y = 0
                    for line in lines:
                        bbox = draw.textbbox((0, 0), line, font=font)
                        tw = bbox[2] - bbox[0]
                        th = bbox[3] - bbox[1]
                        if align == "center":
                            x = max(0, (w - tw) // 2)
                        elif align == "right":
                            x = max(0, w - tw)
                        else:
                            x = 0
                        draw.text((x, y), line, font=font, fill=color + (255,))
                        y += th
                    arr = np.array(bg)
                    end = min(start + dur, total_duration)
                    new_dur = max(0.0, end - start)
                    if new_dur <= 0:
                        continue
                    clip = ImageClip(arr)
                    clip = _with_duration(clip, new_dur)
                    clip = _with_start(_with_position(clip, pos), start)
                    clips.append(clip)
                elif media_type == "audio":
                    url_a = s.get("mediaUrlRemote")
                    if not url_a:
                        continue
                    local_path = _download_to_temp(url_a, suffix=os.path.splitext(url_a)[1]) if url_a.startswith("http") else url_a
                    try:
                        a = AudioFileClip(local_path)
                    except Exception:
                        continue
                    trim_before = s.get("trimBefore")
                    if trim_before:
                        tb = float(trim_before)
                        if tb > 1000:
                            tb = tb / 1000.0
                        a = a.subclip(tb, min(tb + dur, getattr(a, "duration", dur)))
                    else:
                        a = a.subclip(0, min(dur, getattr(a, "duration", dur)))
                    if hasattr(a, "set_start"):
                        a = a.set_start(start)
                    elif hasattr(a, "with_start"):
                        a = a.with_start(start)
                    audio_clips.append(a)
                else:
                    continue
            except Exception:
                # Skip broken media entries
                continue

    comp = CompositeVideoClip(clips, size=(width, height))
    if audio_clips:
        try:
            comp.audio = CompositeAudioClip(audio_clips)
        except Exception:
            comp.audio = None

    # Render to a temp mp4 file
    temp_dir = tempfile.mkdtemp(prefix="render_")
    out_path = os.path.join(temp_dir, "output.mp4")
    try:
        comp.write_videofile(
            out_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            bitrate="2500k",
            audio_bitrate="192k",
        )
    except TypeError:
        # Fallback for MoviePy versions with different signatures
        comp.write_videofile(out_path, fps=fps)
    finally:
        comp.close()

    # Stream back result
    def _file_iterator(path: str, chunk_size: int = 1024 * 1024):
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    headers = {
        "Content-Disposition": 'attachment; filename="render.mp4"',
    }
    return StreamingResponse(_file_iterator(out_path), media_type="video/mp4", headers=headers)
