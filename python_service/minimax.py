import json
import os
import tempfile
import time
from pathlib import Path

import httpx


def _config() -> tuple[str, str]:
    api_key = os.getenv("MINIMAX_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("缺少 MINIMAX_API_KEY，请在 .env 中配置")
    base_url = os.getenv("MINIMAX_API_BASE_URL", "https://api.minimaxi.com").rstrip("/")
    return api_key, base_url


def _request(method: str, path: str, payload: dict) -> dict:
    api_key, base_url = _config()
    with httpx.Client(timeout=120) as client:
        response = client.request(
            method,
            f"{base_url}{path}",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
    data = response.json()
    if data.get("base_resp", {}).get("status_code") not in (0, None):
        raise RuntimeError(data.get("base_resp", {}).get("status_msg", "MiniMax API 请求失败"))
    return data


def generate_music(payload: dict) -> dict:
    """Generate background music via MiniMax Music 3.0.
    
    Parameters:
        prompt: Music style/emotion description (e.g., "轻快电子，夏日氛围")
        duration: Target duration in seconds (default 15)
        instrumental: Generate pure instrumental (default True)
    
    Returns: {ok, music_url, duration, prompt}
    """
    prompt = str(payload.get("prompt") or "轻快愉悦的背景音乐").strip()
    instrumental = payload.get("instrumental", True)
    duration = int(payload.get("duration") or 15)

    # Enhance prompt for instrumental BGM
    if instrumental:
        prompt = f"纯音乐背景配乐，{prompt}，无歌词无人声，适合短视频配乐"

    request_body = {
        "model": payload.get("model") or os.getenv("MINIMAX_MUSIC_MODEL", "music-3.0"),
        "prompt": prompt,
        "is_instrumental": instrumental,
        "audio_setting": {
            "sample_rate": 44100,
            "bitrate": 256000,
            "format": "mp3",
        },
        "output_format": "url",
    }

    data = _request("POST", "/v1/music_generation", request_body)
    music_url = data.get("audio_url") or data.get("data", {}).get("audio_url") or ""

    if not music_url:
        raise RuntimeError("MiniMax 未返回音乐地址")

    return {
        "ok": True,
        "provider": "minimax",
        "model": request_body["model"],
        "music_url": music_url,
        "prompt": payload.get("prompt", ""),
        "instrumental": instrumental,
    }


def download_music(music_url: str, target: Path) -> Path:
    """Download generated music to local file."""
    if not music_url.startswith(("http://", "https://")):
        raise ValueError("音乐地址无效")
    with httpx.stream("GET", music_url, timeout=120, follow_redirects=True, verify=False) as response:
        response.raise_for_status()
        with target.open("wb") as output:
            for chunk in response.iter_bytes():
                output.write(chunk)
    return target
