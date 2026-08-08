"""Upload files to the configured public 火山 TOS bucket."""
import os
import uuid
from datetime import datetime

import httpx


def _tos_base() -> str:
    configured = os.getenv("TOS_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        if not configured.startswith("https://"):
            raise RuntimeError("TOS_PUBLIC_BASE_URL 必须是 HTTPS 地址")
        return configured

    bucket = os.getenv("TOS_BUCKET", "").strip()
    if not bucket or bucket.startswith("YOUR_"):
        raise RuntimeError("缺少 TOS_PUBLIC_BASE_URL 或 TOS_BUCKET")
    region = os.getenv("TOS_REGION", "cn-beijing").strip()
    return f"https://{bucket}.tos-{region}.volces.com"


def mirror_video_to_tos(video_url: str, filename: str = "") -> dict:
    """Download a video from a URL and upload it to TOS. Returns {ok, url, key}."""
    if not video_url:
        return {"ok": False, "error": "empty_url"}
    tos_base = _tos_base()

    name = filename or f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.mp4"
    key = f"videos/{name}"

    # Download video
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        dl_resp = client.get(video_url)
        dl_resp.raise_for_status()
        video_bytes = dl_resp.content

    # Upload to TOS
    with httpx.Client(timeout=60) as client:
        put_resp = client.put(
            f"{tos_base}/{key}",
            content=video_bytes,
            headers={"Content-Type": "video/mp4"},
        )
        put_resp.raise_for_status()

    public_url = f"{tos_base}/{key}"
    return {"ok": True, "name": name, "url": public_url, "key": key, "size_bytes": len(video_bytes)}
