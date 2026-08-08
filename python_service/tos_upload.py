"""Upload files to the configured public 火山 TOS bucket."""
import os
import uuid
from datetime import datetime

import httpx

TOS_BUCKET = os.getenv("TOS_BUCKET", "steady-store-aigc")
TOS_REGION = os.getenv("TOS_REGION", "cn-beijing")
TOS_BASE = os.getenv(
    "TOS_PUBLIC_BASE_URL",
    f"https://{TOS_BUCKET}.tos-{TOS_REGION}.volces.com",
).rstrip("/")


def mirror_video_to_tos(video_url: str, filename: str = "") -> dict:
    """Download a video from a URL and upload it to TOS. Returns {ok, url, key}."""
    if not video_url:
        return {"ok": False, "error": "empty_url"}

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
            f"{TOS_BASE}/{key}",
            content=video_bytes,
            headers={"Content-Type": "video/mp4"},
        )
        put_resp.raise_for_status()

    public_url = f"{TOS_BASE}/{key}"
    return {"ok": True, "name": name, "url": public_url, "key": key, "size_bytes": len(video_bytes)}
