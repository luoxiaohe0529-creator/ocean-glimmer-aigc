import json
import os
import subprocess
import tempfile
from pathlib import Path

import httpx

from .media import _download, _ffmpeg_path


def _config() -> tuple[str, str]:
    api_key = os.getenv("TOPAZ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("缺少 TOPAZ_API_KEY")
    return api_key, os.getenv("TOPAZ_API_BASE_URL", "https://api.topazlabs.com").rstrip("/")


def _probe(path: Path) -> dict:
    ffmpeg = _ffmpeg_path()
    result = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )
    stderr = result.stderr
    # Parse resolution from ffmpeg stderr
    import re as _re
    stream_match = _re.search(r'Stream #\d+:\d+(?:\(\w+\))?: Video:.*?, (\d+)x(\d+)', stderr)
    width = int(stream_match.group(1)) if stream_match else 1280
    height = int(stream_match.group(2)) if stream_match else 720
    fps_match = _re.search(r'(\d+(?:\.\d+)?)\s*(?:fps|FPS)', stderr)
    frame_rate = float(fps_match.group(1)) if fps_match else 30.0
    dur_match = _re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', stderr)
    if dur_match:
        duration = int(dur_match.group(1)) * 3600 + int(dur_match.group(2)) * 60 + float(dur_match.group(3))
    else:
        duration = 15.0
    return {
        "width": width,
        "height": height,
        "frame_rate": round(frame_rate, 3),
        "duration": duration,
        "frame_count": int(round(duration * frame_rate)),
        "size": path.stat().st_size,
    }


def _topaz_request(method: str, path: str, *, payload: dict | None = None) -> dict:
    api_key, base_url = _config()
    with httpx.Client(timeout=120) as client:
        response = client.request(method, f"{base_url}{path}", headers={"X-API-Key": api_key}, json=payload)
        response.raise_for_status()
        return response.json() if response.content else {}


def _request_id(data: dict) -> str:
    return str(data.get("requestId") or data.get("request_id") or data.get("id") or data.get("data", {}).get("requestId") or "")


def _upload_parts(path: Path, accepted: dict) -> list[dict]:
    raw_urls = accepted.get("uploadUrls") or accepted.get("upload_urls") or accepted.get("urls") or accepted.get("data", {}).get("uploadUrls") or []
    if isinstance(raw_urls, str):
        raw_urls = [raw_urls]
    parts = []
    part_size = int(accepted.get("partSize") or accepted.get("part_size") or accepted.get("data", {}).get("partSize") or path.stat().st_size)
    with path.open("rb") as source, httpx.Client(timeout=300) as client:
        for index, entry in enumerate(raw_urls, start=1):
            url = entry if isinstance(entry, str) else entry.get("url") or entry.get("uploadUrl")
            if not url:
                continue
            chunk = source.read(part_size)
            response = client.put(url, content=chunk, headers={"Content-Type": "video/mp4"})
            response.raise_for_status()
            parts.append({"partNum": index, "eTag": response.headers.get("etag", "").strip('"')})
    if not parts:
        raise RuntimeError("Topaz 未返回上传地址")
    return parts


def create_enhancement_task(payload: dict) -> dict:
    source_url = str(payload.get("source_video_url") or "").strip()
    if not source_url:
        raise ValueError("缺少待增强视频")
    with tempfile.TemporaryDirectory(prefix="adflow-topaz-") as directory:
        source = Path(directory) / "source.mp4"
        _download(source_url, source)
        meta = _probe(source)
        target_edges = {"1080p": 1080, "2k": 1440, "4k": 2160}
        target = target_edges.get(str(payload.get("target_resolution") or "").lower())
        requested_scale = (target / min(meta["width"], meta["height"])) if target else float(payload.get("upscale_factor") or 2)
        scale = max(1.0, min(4.0, requested_scale))
        output_width = int(round(meta["width"] * scale / 2) * 2)
        output_height = int(round(meta["height"] * scale / 2) * 2)
        model = payload.get("model") or os.getenv("TOPAZ_VIDEO_MODEL", "ghq-5")
        request = {
            "source": {
                "resolution": {"width": meta["width"], "height": meta["height"]},
                "container": "mp4", "size": meta["size"], "duration": meta["duration"],
                "frameRate": meta["frame_rate"], "frameCount": meta["frame_count"],
            },
            "output": {
                "resolution": {"width": output_width, "height": output_height},
                "audioCodec": "AAC", "audioTransfer": "Copy", "frameRate": meta["frame_rate"],
                "videoEncoder": "H265", "dynamicCompressionLevel": "High", "container": "mp4",
            },
            "filters": [{"model": model}],
        }
        created = _topaz_request("POST", "/video/", payload=request)
        request_id = _request_id(created)
        if not request_id:
            raise RuntimeError("Topaz 未返回 requestId")
        accepted = _topaz_request("PATCH", f"/video/{request_id}/accept")
        upload_results = _upload_parts(source, accepted)
        _topaz_request("PATCH", f"/video/{request_id}/complete-upload/", payload={"uploadResults": upload_results})
    return {"ok": True, "provider": "topaz", "kind": "video_enhancement", "model": model, "task_id": request_id, "status": "queued"}


def query_enhancement_task(payload: dict) -> dict:
    request_id = str(payload.get("task_id") or payload.get("request_id") or "").strip()
    if not request_id:
        raise ValueError("缺少 task_id")
    data = _topaz_request("GET", f"/video/{request_id}/status")
    raw_status = str(data.get("status") or data.get("state") or data.get("data", {}).get("status") or "unknown").lower()
    status = {"completed": "succeeded", "complete": "succeeded", "success": "succeeded", "processing": "running", "queued": "running", "failed": "failed", "error": "failed"}.get(raw_status, raw_status)
    url = data.get("downloadUrl") or data.get("download_url") or data.get("outputUrl") or data.get("output_url") or data.get("data", {}).get("downloadUrl") or ""
    return {"ok": True, "provider": "topaz", "task_id": request_id, "status": status, "urls": [url] if url else [], "raw": data}
