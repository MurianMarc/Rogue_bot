from __future__ import annotations

import os
import shutil
from pathlib import Path


def add_bundled_ffmpeg_to_path() -> None:
    runtime_bin = Path(".runtime") / "bin"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    _prepend_path(runtime_bin)

    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    try:
        import imageio_ffmpeg
    except Exception:
        return

    ffmpeg_path = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not ffmpeg_path.exists():
        return

    target = runtime_bin / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not target.exists():
        shutil.copy2(ffmpeg_path, target)

    _prepend_path(runtime_bin)


def _prepend_path(path: Path) -> None:
    ffmpeg_dir = str(path.resolve())
    current_path = os.environ.get("PATH", "")
    if ffmpeg_dir not in current_path.split(os.pathsep):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path
