"""Upload files to the configured public 火山 TOS bucket."""
import base64
import os
import uuid
from datetime import datetime

import httpx
import tos


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


def upload_images(images: list[dict]) -> dict:
    """Upload browser image data URLs with authenticated TOS requests."""
    if not images:
        raise ValueError("图片请求格式无效")
    access_key = os.getenv("TOS_ACCESS_KEY_ID", "").strip()
    secret_key = os.getenv("TOS_SECRET_ACCESS_KEY", "").strip()
    bucket = os.getenv("TOS_BUCKET", "").strip()
    region = os.getenv("TOS_REGION", "cn-beijing").strip()
    if not access_key or not secret_key or not bucket:
        raise RuntimeError("缺少 TOS 上传凭据")
    endpoint = os.getenv("TOS_ENDPOINT", f"tos-{region}.volces.com").strip()
    client = tos.TosClientV2(access_key, secret_key, endpoint, region)
    public_base = _tos_base()
    extensions = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}
    results = []
    for image in images[:9]:
        name = str(image.get("name") or "product-image")
        data_url = str(image.get("dataUrl") or "")
        if not data_url.startswith("data:image/") or ";base64," not in data_url:
            raise ValueError(f"{name} 不是支持的图片格式")
        header, encoded = data_url.split(",", 1)
        mime_type = header[5:].split(";", 1)[0].lower()
        extension = extensions.get(mime_type)
        if not extension:
            raise ValueError(f"{name} 不是支持的图片格式")
        binary = base64.b64decode(encoded, validate=True)
        key = f"images/{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex}.{extension}"
        client.put_object(bucket, key, content=binary, content_length=len(binary), content_type=mime_type)
        results.append({"ok": True, "name": name, "url": f"{public_base}/{key}", "storage": "tos"})
    return {"ok": True, "images": results}


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
