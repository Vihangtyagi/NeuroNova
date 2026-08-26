"""
voice.py — offline text-to-speech using the espeak-ng system binary.

No internet or API key required, which matters for low-connectivity
areas of the North Eastern Region. If espeak-ng is not installed on the
host machine, functions fail gracefully and the caller should fall back
to showing text only.
"""

import subprocess
import shutil
import tempfile
import os

_ESPEAK = shutil.which("espeak-ng") or shutil.which("espeak")


def is_available():
    return _ESPEAK is not None


def speak_to_file(text, speed_wpm=150):
    """
    Render `text` to a temporary .wav file and return its path,
    or None if no TTS engine is available on this machine.
    """
    if not _ESPEAK:
        return None
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            [_ESPEAK, "-s", str(speed_wpm), "-w", path, text],
            check=True,
            capture_output=True,
            timeout=15,
        )
        return path
    except Exception:
        return None
