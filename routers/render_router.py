import math
import os
import tempfile
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.database import get_db
from core.auth import get_current_user
from core.config import settings
import requests


router = APIRouter(prefix="/render", tags=["Render"])


def _compute_timeline_duration_seconds(timeline_tracks: List[Dict[str, Any]], pps: float) -> float:
    max_end = 0.0
    for track in timeline_tracks or []:
        for s in track.get("scrubbers", []) or []:
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


def _local_media_path_from_url(url: str) -> str | None:
    try:
        if settings.MEDIA_URL_PATH in url:
            fname = os.path.basename(url)
            candidate = os.path.join(settings.MEDIA_DIR, fname)
            if os.path.exists(candidate):
                return candidate
    except Exception:
        pass
    return None


def _resolve_media_path(item: Dict[str, Any]) -> str | None:
    url = (
        item.get("mediaUrlRemote")
        or item.get("mediaUrlLocal")
        or item.get("src")
        or item.get("url")
        or None
    )
    if url:
        print(f"[render] Resolving URL: {url}")
        local = _local_media_path_from_url(url)
        if local:
            print(f"[render] Found local path: {local}")
            return local
        if not isinstance(url, str) or not url.startswith("http"):
            return url
        print(f"[render] Downloading from URL: {url}")
        return url
    name = item.get("name")
    if name:
        p = os.path.join(settings.MEDIA_DIR, name)
        if os.path.exists(p):
            print(f"[render] Found local file: {p}")
            return p
    print(f"[render] No valid media path found for item: {item}")
    return None


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
        if hasattr(clip, "resize"):
            try:
                return clip.resize(newsize=size)
            except TypeError:
                return clip.resize(size)
        if hasattr(clip, "with_size"):
            return clip.with_size(size)
        return clip

    timeline_raw = payload.get("timelineData") or payload.get("timeline") or []
    tracks = timeline_raw.get("tracks") if isinstance(timeline_raw, dict) else (timeline_raw or [])
    width = int(payload.get("compositionWidth") or 1920)
    height = int(payload.get("compositionHeight") or 1080)
    frames = int(payload.get("visualDurationInFrames") or payload.get("durationInFrames") or 0)
    pps = float(payload.get("getPixelsPerSecond") or 100.0)

    fps = int(payload.get("fps") or 30)
    fps = max(24, min(60, fps))
    timeline_seconds = 0.0
    if frames > 0:
        total_duration = max(1.0 / fps, frames / fps)
    else:
        timeline_seconds = _compute_timeline_duration_seconds(tracks, pps)
        total_duration = max(1.0 / fps, timeline_seconds or (1.0 * 10 / fps))

    base = _with_duration(ColorClip(size=(width, height), color=(0, 0, 0)), total_duration)

    clips = [base]
    audio_clips = []
    audio_max_end = 0.0
    visual_items: List[Dict[str, Any]] = []

    # Debug logs to track audio clips and media resolution
    print(f"[render] Number of audio clips initially: {len(audio_clips)}")
    # Sort tracks so that higher-numbered tracks are on top.
    def _track_num(t: Dict[str, Any]) -> int:
        n = t.get("trackNumber")
        try:
            if n is not None:
                return int(n)
        except Exception:
            pass
        tid = str(t.get("id") or "")
        if tid.startswith("track-"):
            try:
                return int(tid.split("-", 1)[1])
            except Exception:
                return 0
        return 0

    tracks_sorted = sorted(tracks or [], key=_track_num)
    print(f"[render] Track order (bottom->top): {[(_track_num(t), t.get('id')) for t in tracks_sorted]}")

    for track in tracks_sorted:
        for s in track.get("scrubbers", []):
            media_type = (s.get("mediaType") or "").lower()
            url = _resolve_media_path(s)
            if not url:
                continue

            print(f"[render] Resolving media path for {s.get('name')}: {url}")

            start = float(s.get("startTime") or (float(s.get("left", 0)) / pps if pps else 0))
            dur = float(s.get("duration") or (float(s.get("width", 0)) / pps if pps else 0))

            if dur <= 0:
                continue

            left = int(s.get("left_player", 0) or 0)
            top = int(s.get("top_player", 0) or 0)
            w_px = int(s.get("width_player", 0) or 0)
            h_px = int(s.get("height_player", 0) or 0)
            pos = (left, top)
            track_index = 0
            try:
                track_index = int(s.get("trackIndex") or 0)
            except Exception:
                track_index = 0

            try:
                if media_type == "audio":
                    print(f"[render] Loading audio file: {url}")
                    try:
                        a = AudioFileClip(url)

                        # Timeline from frontend
                        start = float(s.get("startTime", 0))
                        requested_dur = float(s.get("duration", a.duration))

                        # CLAMP duration to avoid reading out-of-range
                        safe_duration = min(requested_dur, a.duration)

                        print(f"[render] Audio timing → start={start}, duration={safe_duration} (requested={requested_dur}, actual={a.duration})")

                        # Trim using with_duration() (MoviePy v2)
                        a = a.with_duration(safe_duration)

                        # Apply start time
                        a = a.with_start(start)

                        audio_clips.append(a)

                    except Exception as e:
                        print(f"[render] Error loading audio clip {url}: {e}")



                elif media_type == "image":
                    # Defer creating clip; layer order will be applied by trackIndex.
                    visual_items.append({
                        "type": "image",
                        "url": url,
                        "start": start,
                        "dur": dur,
                        "pos": pos,
                        "size": (w_px, h_px),
                        "trackIndex": track_index,
                        "name": s.get("name"),
                    })
                    print(f"[render] Queued image for layering: idx={track_index} url={url}")
                else:
                    print(f"[render] Skipping non-audio/media type: {media_type}")
            except Exception as e:
                print(f"[render] Error processing scrubber: {e}")

    # After processing all tracks, check if audio is added
    print(f"[render] Number of audio clips: {len(audio_clips)}")

    # Sort and realize visual items according to trackIndex bottom->top
    visual_items_sorted = sorted(visual_items, key=lambda x: int(x.get("trackIndex", 0)), reverse=True)
    print("[render] Visual layering order (top->bottom):", [(v.get("trackIndex"), v.get("name")) for v in visual_items_sorted])
    for v in visual_items_sorted:
        try:
            if v["type"] == "image":
                img_clip = ImageClip(v["url"])
                img_clip = _with_duration(img_clip, v["dur"])
                w_px, h_px = v["size"]
                img_clip = _resize(img_clip, (w_px, h_px)) if w_px and h_px else img_clip
                img_clip = _with_position(img_clip, v["pos"])
                img_clip = _with_start(img_clip, v["start"])
                clips.append(img_clip)
        except Exception as e:
            print(f"[render] Error building visual clip {v.get('name')}: {e}")

    # Initialize comp (video composition) if no video clips were added
    if not clips:
        clips.append(base)

    # Proceed with video creation if audio clips are available
    if audio_clips:
        print(f"[render] Combining audio clips into final video...")
        mixed_audio = CompositeAudioClip(audio_clips)
        mixed_audio = mixed_audio.with_duration(total_duration)  # Corrected the method
        comp = CompositeVideoClip(clips, size=(width, height))
        comp = comp.with_audio(mixed_audio)  # Corrected the method to `with_audio`
    else:
        comp = CompositeVideoClip(clips, size=(width, height))

    temp_dir = tempfile.mkdtemp(prefix="render_")
    out_path = os.path.join(temp_dir, "output.mp4")
    try:
        print(f"[render] Rendering video with audio clips count: {len(audio_clips)}")
        comp.write_videofile(
            out_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            audio=True,
            audio_fps=44100,
            temp_audiofile=os.path.join(temp_dir, "temp-audio.m4a"),
            bitrate="2500k",
            audio_bitrate="192k",
            threads=0,
        )
    except Exception as e:
        try:
            print(f"[render] Error with AAC codec, trying MP3 codec: {e}")
            comp.write_videofile(
                out_path,
                fps=fps,
                codec="libx264",
                audio_codec="libmp3lame",
                audio=True,
                audio_fps=44100,
                temp_audiofile=os.path.join(temp_dir, "temp-audio.mp3"),
                bitrate="2500k",
                audio_bitrate="192k",
                threads=0,
            )
        except Exception as e2:
            comp.close()
            raise HTTPException(status_code=500, detail=f"Render failed (audio): {e2}")
    finally:
        comp.close()

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
