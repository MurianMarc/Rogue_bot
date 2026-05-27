from __future__ import annotations

import asyncio
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message
from neonize.utils.message import get_message_type

from .config import Settings
from .ffmpeg import add_bundled_ffmpeg_to_path


@dataclass(frozen=True, slots=True)
class CreatedSticker:
    webp: bytes
    animated: bool
    source_path: Path
    sticker_path: Path


async def create_sticker(
    media: bytes,
    source: Message,
    settings: Settings,
    name: str,
) -> CreatedSticker:
    return await asyncio.to_thread(_create_sticker, media, source, settings, name)


def sticker_summary(settings: Settings) -> str:
    store = settings.sticker_store_dir
    if not store.exists():
        return f"No stickers stored yet. Folder: {store}"
    stickers = sorted(store.glob("*.webp"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not stickers:
        return f"No stickers stored yet. Folder: {store}"
    latest = "\n".join(f"- {path.name}" for path in stickers[:5])
    return "\n".join(
        [
            f"Stored stickers: {len(stickers)}",
            f"Folder: {store}",
            "Latest:",
            latest,
        ]
    )


def _create_sticker(
    media: bytes,
    source: Message,
    settings: Settings,
    name: str,
) -> CreatedSticker:
    max_bytes = settings.sticker_max_input_mb * 1024 * 1024
    if len(media) > max_bytes:
        raise RuntimeError(
            f"Media is too large for sticker mode. Keep it under "
            f"{settings.sticker_max_input_mb} MB."
        )

    store = settings.sticker_store_dir
    store.mkdir(parents=True, exist_ok=True)

    mime = _source_mime(source, media)
    if not settings.sticker_animated_enabled and (
        mime == "image/gif" or mime.startswith("video/")
    ):
        raise RuntimeError("Animated/video stickers are disabled in low-memory mode.")

    stem = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    source_path = store / f"{stem}{_extension_for_mime(mime)}"
    sticker_path = store / f"{stem}.webp"
    source_path.write_bytes(media)

    if mime == "image/webp":
        webp = media
        sticker_path.write_bytes(webp)
        return CreatedSticker(webp, _has_multiple_frames(media), source_path, sticker_path)

    if mime.startswith("image/") and mime != "image/gif":
        webp = _static_image_to_webp(
            media,
            crop=settings.sticker_crop,
            name=name,
            packname=settings.sticker_pack_name,
        )
        sticker_path.write_bytes(webp)
        return CreatedSticker(webp, False, source_path, sticker_path)

    webp = _animated_media_to_webp(source_path, sticker_path, settings)
    return CreatedSticker(webp, True, source_path, sticker_path)


def _source_mime(source: Message, media: bytes) -> str:
    message_type = get_message_type(source)
    mime = (getattr(message_type, "mimetype", "") or "").casefold()
    if mime:
        return mime
    try:
        import magic
    except Exception:
        return "application/octet-stream"
    return (magic.from_buffer(media, mime=True) or "application/octet-stream").casefold()


def _static_image_to_webp(media: bytes, crop: bool, name: str, packname: str) -> bytes:
    from PIL import Image, ImageOps
    from neonize.utils.sticker import add_exif

    image = Image.open(BytesIO(media))
    image = ImageOps.exif_transpose(image).convert("RGBA")

    if crop:
        image = ImageOps.fit(image, (512, 512), method=Image.Resampling.LANCZOS)
    else:
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        left = (512 - image.width) // 2
        top = (512 - image.height) // 2
        canvas.alpha_composite(image, (left, top))
        image = canvas

    for quality in (90, 80, 70, 60):
        output = BytesIO()
        image.save(
            output,
            format="webp",
            quality=quality,
            method=6,
            exif=add_exif(name=name, packname=packname),
        )
        if output.tell() <= 512000 or quality == 60:
            return output.getvalue()
    return output.getvalue()


def _animated_media_to_webp(source_path: Path, sticker_path: Path, settings: Settings) -> bytes:
    add_bundled_ffmpeg_to_path()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for GIF/video stickers. Run install_ffmpeg.ps1.")

    attempts = (
        ((min(settings.sticker_animated_fps, 8), 45),)
        if settings.low_memory_mode
        else (
            (settings.sticker_animated_fps, 70),
            (12, 60),
            (10, 50),
            (8, 45),
        )
    )
    filter_chain = (
        "scale=512:512:force_original_aspect_ratio=decrease,"
        "fps={fps},"
        "pad=512:512:(ow-iw)/2:(oh-ih)/2:color=white@0.0"
    )

    last_error = ""
    for fps, quality in attempts:
        if sticker_path.exists():
            sticker_path.unlink()
        command = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-t",
            str(settings.sticker_animated_seconds),
            "-i",
            str(source_path),
            "-an",
            "-threads",
            "1",
            "-vcodec",
            "libwebp_anim",
            "-vf",
            filter_chain.format(fps=fps),
            "-loop",
            "0",
            "-preset",
            "picture",
            "-q:v",
            str(quality),
            "-fs",
            "512000",
            str(sticker_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and sticker_path.exists() and sticker_path.stat().st_size:
            return sticker_path.read_bytes()
        last_error = (result.stderr or result.stdout or "unknown ffmpeg error").strip()

    raise RuntimeError(f"FFmpeg could not convert this media: {last_error}")


def _has_multiple_frames(media: bytes) -> bool:
    try:
        from PIL import Image, ImageSequence

        image = Image.open(BytesIO(media))
        return len(ImageSequence.all_frames(image)) > 1
    except Exception:
        return False


def _extension_for_mime(mime: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov",
    }.get(mime, ".bin")
