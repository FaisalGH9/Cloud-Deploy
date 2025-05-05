"""
YouTube service using pytubefix with cookies support 
"""
import os
import re
import hashlib
import asyncio
import urllib.request
from typing import Dict, Any

from pytubefix import YouTube
from pydub import AudioSegment

from config.settings import (
    MEDIA_DIR,
    AUDIO_FORMAT,
    DEFAULT_AUDIO_QUALITY,
    LONG_AUDIO_QUALITY,
    LONG_VIDEO_THRESHOLD
)

# Load proxy URL from environment
PROXY_URL = os.getenv("PROXY_URL")
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
if PROXY_URL:
    os.environ["HTTP_PROXY"] = PROXY_URL
    os.environ["HTTPS_PROXY"] = PROXY_URL

# === Cookies setup ===
COOKIES_FILE = r"C:\Users\HUAWEI\Desktop\cookies.txt"

def load_cookies() -> str:
    if not os.path.exists(COOKIES_FILE):
        print("⚠️ cookies.txt not found. Continuing without cookies.")
        return ""
    with open(COOKIES_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    cookies = []
    for line in lines:
        if not line.startswith("#") and "\t" in line:
            parts = line.strip().split("\t")
            if len(parts) >= 7:
                cookies.append(f"{parts[5]}={parts[6]}")
    return "; ".join(cookies)

cookies_header = load_cookies()
if cookies_header:
    opener = urllib.request.build_opener()
    opener.addheaders.append(("Cookie", cookies_header))
    urllib.request.install_opener(opener)
    print("✅ Cookies injected into urllib requests.")


class YouTubeService:
    """Handles YouTube audio extraction and processing using pytubefix"""

    def extract_video_id(self, url: str) -> str:
        regex = r"(youtu\.be\/|youtube\.com\/(watch\?(.*&)?v=|embed\/|v\/|shorts\/))([^?&\"'>]+)"
        m = re.search(regex, url)
        if m:
            return m.group(4)
        return hashlib.md5(url.encode()).hexdigest()

    async def download_audio(self, url: str, options: Dict[str, Any]) -> str:
        """
        Download and process audio asynchronously using pytubefix
        """
        vid = self.extract_video_id(url)
        safe_vid = re.sub(r"[^a-zA-Z0-9_-]", "", vid)  # ✅ sanitize
        base = os.path.join(MEDIA_DIR, safe_vid)
        target = f"{base}.{AUDIO_FORMAT}"

        # ✅ Ensure media dir exists
        os.makedirs(MEDIA_DIR, exist_ok=True)

        if os.path.exists(target):
            return target

        loop = asyncio.get_event_loop()
        yt = await loop.run_in_executor(None, lambda: YouTube(url))
        stream = yt.streams.filter(only_audio=True).first()
        if not stream:
            raise RuntimeError("❌ No audio stream found using pytubefix")

        def _download_stream(s, out_path, fname):
            return s.download(output_path=out_path, filename=fname)

        temp_filename = f"{safe_vid}_temp"
        temp_path = await loop.run_in_executor(None, _download_stream, stream, MEDIA_DIR, temp_filename)

        print(f"✅ [DEBUG] Downloaded temp audio to: {temp_path}")

        # Convert to desired format
        audio = AudioSegment.from_file(temp_path)
        bitrate = DEFAULT_AUDIO_QUALITY if yt.length <= LONG_VIDEO_THRESHOLD else LONG_AUDIO_QUALITY
        audio.export(target, format=AUDIO_FORMAT, bitrate=bitrate)
        os.remove(temp_path)

        # Apply duration limit
        dur_opt = options.get('duration', 'full_video')
        if dur_opt != 'full_video':
            target = await self._process_duration_limit(target, dur_opt)

        return target

    async def _process_duration_limit(self, path: str, duration: str) -> str:
        limits = {
            'first_5_minutes': 5 * 60 * 1000,
            'first_10_minutes': 10 * 60 * 1000,
            'first_30_minutes': 30 * 60 * 1000,
            'first_60_minutes': 60 * 60 * 1000,
        }
        ms = limits.get(duration)
        if not ms:
            return path
        trimmed = path.replace(f".{AUDIO_FORMAT}", f"_{duration}.{AUDIO_FORMAT}")
        if os.path.exists(trimmed):
            return trimmed
        loop = asyncio.get_event_loop()
        sound = await loop.run_in_executor(None, AudioSegment.from_file, path)
        clip = sound[:ms]
        await loop.run_in_executor(None, lambda: clip.export(trimmed, format=AUDIO_FORMAT))
        return trimmed
