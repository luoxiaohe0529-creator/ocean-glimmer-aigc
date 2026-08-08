import json
import os

import httpx


def _config() -> tuple[str, str]:
    api_key = os.getenv("KIE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("缺少 KIE_API_KEY")
    base_url = os.getenv("KIE_API_BASE_URL", "https://api.kie.ai").rstrip("/")
    return api_key, base_url


def _request(method: str, path: str, *, json: dict | None = None, params: dict | None = None) -> dict:
    api_key, base_url = _config()
    with httpx.Client(timeout=90) as client:
        response = client.request(
            method,
            f"{base_url}{path}",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=json,
            params=params,
        )
        response.raise_for_status()
    data = response.json()
    if data.get("code") not in (None, 200):
        raise RuntimeError(data.get("msg") or "KIE API 请求失败")
    return data


def create_image_task(kind: str, payload: dict) -> dict:
    if kind == "character":
        input_urls = payload.get("input_urls") or payload.get("reference_images") or []
        model = payload.get("model") or os.getenv(
            "KIE_CHARACTER_MODEL",
            "gpt-image-2-image-to-image" if input_urls else "gpt-image-2-text-to-image",
        )
        task_input = {
            "prompt": payload.get("prompt") or payload.get("character_description") or "",
            "aspect_ratio": payload.get("aspect_ratio") or "9:16",
            "resolution": payload.get("resolution") or "2K",
        }
        if input_urls:
            task_input["input_urls"] = input_urls
    elif kind == "storyboard":
        model = os.getenv("KIE_STORYBOARD_MODEL", "nano-banana-pro")
        task_input = {
            "prompt": payload.get("prompt") or "",
            "image_input": payload.get("image_input") or payload.get("reference_images") or [],
            "aspect_ratio": payload.get("aspect_ratio") or "9:16",
            "resolution": payload.get("resolution") or "1K",
            "output_format": payload.get("output_format") or "png",
        }
    else:
        raise ValueError("未知图片任务类型")

    request_body = {"model": model, "input": task_input}
    callback_url = payload.get("callback_url") or os.getenv("KIE_CALLBACK_URL", "").strip()
    if callback_url:
        request_body["callBackUrl"] = callback_url
    data = _request("POST", "/api/v1/jobs/createTask", json=request_body)
    return {
        "ok": True,
        "provider": "kie.ai",
        "kind": kind,
        "model": model,
        "task_id": data.get("data", {}).get("taskId"),
        "raw": data,
    }


def create_overseas_video_task(payload: dict) -> dict:
    request_body = {
        "prompt": payload.get("prompt") or "",
        "imageUrls": payload.get("image_urls") or [],
        "model": payload.get("model") or os.getenv("KIE_OVERSEAS_VIDEO_MODEL", "veo3_fast"),
        "aspect_ratio": payload.get("aspect_ratio") or "9:16",
        "enableFallback": bool(payload.get("enable_fallback", True)),
        "enableTranslation": bool(payload.get("enable_translation", True)),
        "generationType": payload.get("generation_type") or (
            "REFERENCE_2_VIDEO" if payload.get("image_urls") else "TEXT_2_VIDEO"
        ),
    }
    callback_url = payload.get("callback_url") or os.getenv("KIE_CALLBACK_URL", "").strip()
    if callback_url:
        request_body["callBackUrl"] = callback_url
    data = _request("POST", "/api/v1/veo/generate", json=request_body)
    return {
        "ok": True,
        "provider": "kie.ai",
        "kind": "overseas_video",
        "model": request_body["model"],
        "task_id": data.get("data", {}).get("taskId"),
        "raw": data,
    }


def create_kling_video_task(payload: dict) -> dict:
    """Create the Chinese-video fallback task after a Seedance policy block."""
    image_urls = payload.get("image_urls") or payload.get("reference_images") or []
    duration = max(3, min(15, int(payload.get("duration") or 5)))
    task_input = {
        "prompt": payload.get("prompt") or payload.get("video_prompt") or "",
        "image_urls": image_urls[:2],
        "sound": bool(payload.get("sound", True)),
        "duration": str(duration),
        "mode": payload.get("mode") or os.getenv("KIE_KLING_VIDEO_MODE", "pro"),
        "multi_shots": False,
    }
    if not image_urls:
        task_input["aspect_ratio"] = payload.get("aspect_ratio") or "9:16"
    model = payload.get("model") or os.getenv("KIE_KLING_VIDEO_MODEL", "kling-3.0/video")
    request_body = {"model": model, "input": task_input}
    callback_url = payload.get("callback_url") or os.getenv("KIE_CALLBACK_URL", "").strip()
    if callback_url:
        request_body["callBackUrl"] = callback_url
    data = _request("POST", "/api/v1/jobs/createTask", json=request_body)
    return {
        "ok": True,
        "provider": "kie.ai",
        "kind": "kling_video",
        "model": model,
        "task_id": data.get("data", {}).get("taskId"),
        "raw": data,
    }


def query_task(payload: dict) -> dict:
    task_id = str(payload.get("task_id") or payload.get("taskId") or "").strip()
    if not task_id:
        raise ValueError("缺少 task_id")
    kind = payload.get("kind") or "image"
    if kind == "overseas_video":
        data = _request("GET", "/api/v1/veo/record-info", params={"taskId": task_id})
        detail = data.get("data") or {}
        flag = detail.get("successFlag")
        status = {0: "running", 1: "succeeded", 2: "failed", 3: "failed"}.get(flag, "unknown")
        urls = (detail.get("response") or {}).get("resultUrls") or []
    else:
        data = _request("GET", "/api/v1/jobs/recordInfo", params={"taskId": task_id})
        detail = data.get("data") or {}
        status = str(detail.get("state") or detail.get("status") or "unknown").lower()
        normalized = {
            "success": "succeeded", "completed": "succeeded", "complete": "succeeded",
            "fail": "failed", "failure": "failed", "error": "failed",
            "processing": "running", "pending": "running", "queued": "running",
        }.get(status, status)
        # Existing image workflows use KIE's native `success`; the Kling branch
        # uses the same terminal vocabulary as the video providers.
        if kind == "kling_video":
            status = normalized
        result = detail.get("resultJson") or {}
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                result = {}
        urls = result.get("resultUrls") or detail.get("resultUrls") or detail.get("result_urls") or []
    return {"ok": True, "provider": "kie.ai", "task_id": task_id, "status": status, "urls": urls, "raw": data}


def save_to_tos(payload: dict) -> dict:
    """Download video from URL and upload to TOS. Called after video generation succeeds."""
    from .tos_upload import mirror_video_to_tos
    video_url = payload.get("video_url", "")
    filename = payload.get("filename", "")
    return mirror_video_to_tos(video_url, filename)
