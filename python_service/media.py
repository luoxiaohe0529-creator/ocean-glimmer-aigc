import base64
import os
import re
import subprocess
import tempfile
import uuid
import json
import zipfile
import shutil
from pathlib import Path


def _ffmpeg_path() -> str:
    configured = os.getenv("FFMPEG_PATH", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        raise RuntimeError(f"FFMPEG_PATH 不可执行或不存在：{path}")
    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered
    raise RuntimeError("找不到 ffmpeg，请安装 ffmpeg 或设置 FFMPEG_PATH")


def _download(url: str, target: Path) -> None:
    if not url.startswith(("http://", "https://")):
        if url.startswith("/"):
            frontend_base_url = os.getenv(
                "FRONTEND_BASE_URL",
                f"http://127.0.0.1:{os.getenv('PORT', '4173')}",
            ).rstrip("/")
            url = f"{frontend_base_url}{url}"
        else:
            raise ValueError("视频地址必须是 HTTP(S) URL")
    result = subprocess.run(
        ["curl", "-sSL", "-o", str(target), "--max-filesize", "629145600", url],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"视频下载失败: {result.stderr[-300:] or 'curl exit ' + str(result.returncode)}")
    if not target.exists() or target.stat().st_size < 100:
        raise RuntimeError("下载的视频文件为空或过小")


def _decode_data_url(value: str, target: Path) -> None:
    match = re.match(r"^data:[^;]+;base64,(.+)$", value, flags=re.S)
    if not match:
        raise ValueError("配乐文件格式无效")
    target.write_bytes(base64.b64decode(match.group(1)))


def _duration(path: Path) -> float:
    probe = subprocess.run(
        [_ffmpeg_path(), "-i", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr)
    if not match:
        return 15.0
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _has_audio(path: Path) -> bool:
    probe = subprocess.run(
        [_ffmpeg_path(), "-i", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(re.search(r"Stream #\d+:\d+(?:\([^)]*\))?: Audio:", probe.stderr))


def _srt_timestamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _write_srt(text: str, duration: float, target: Path, max_chars_per_line: int = 14, max_lines: int = 2) -> None:
    """Smart subtitle chunking — English split by words, Chinese by characters.
    - Chinese: max_chars_per_line chars per line, max_lines lines per screen
    - English: ~42 chars per line (word-boundary), ~84 chars per screen
    - Time allocated proportionally to character count for better voice sync
    """
    alpha_chars = [c for c in text if c.isalpha()]
    ascii_chars = [c for c in text if ord(c) < 128]
    is_english = alpha_chars and len(ascii_chars) / max(len(text), 1) > 0.85

    if is_english:
        # Split by sentence endings first, then by words
        eng_chunks = re.split(r'(?<=[.!?])\s+', text)
        eng_chunks = [c.strip() for c in eng_chunks if c.strip()]
        if not eng_chunks:
            eng_chunks = [text.strip()]
        # Build subtitles by accumulating words up to ~84 chars (2 lines of ~42)
        subtitles: list[str] = []
        buffer = ''
        for chunk in eng_chunks:
            if buffer and len(buffer) + 1 + len(chunk) > 84:
                subtitles.append(buffer.strip())
                buffer = chunk
            elif buffer:
                buffer += ' ' + chunk
            else:
                buffer = chunk
            # If buffer is still long, split it
            while len(buffer) > 84:
                words = buffer.split()
                line1 = []
                line2 = []
                cur = 0
                for w in words:
                    if cur + len(w) <= 42:
                        line1.append(w)
                        cur += len(w) + 1
                    elif cur + len(w) <= 84:
                        line2.append(w)
                        cur += len(w) + 1
                    else:
                        break
                taken = len(line1) + len(line2)
                subtitles.append(' '.join(line1) + '\n' + ' '.join(line2))
                buffer = ' '.join(words[taken:])
        if buffer.strip():
            subtitles.append(buffer.strip())
    else:
        # Chinese: character-based splitting
        max_chars = max_chars_per_line * max_lines
        raw_chunks = re.split(r'(?<=[。！？!?])', text)
        raw_chunks = [c.strip() for c in raw_chunks if c.strip()]
        if not raw_chunks:
            raw_chunks = [text.strip()]
        subtitles = []
        for chunk in raw_chunks:
            remaining = chunk
            while remaining:
                if len(remaining) <= max_chars_per_line:
                    subtitles.append(remaining)
                    break
                elif len(remaining) <= max_chars:
                    mid = len(remaining) // 2
                    for sep in ['，', ',', ' ', '、', '的']:
                        pos = remaining.rfind(sep, mid - 4, mid + 4)
                        if pos > 0:
                            mid = pos + 1
                            break
                    subtitles.append(remaining[:mid].strip() + '\n' + remaining[mid:].strip())
                    break
                else:
                    part = remaining[:max_chars]
                    mid = max_chars_per_line
                    for sep in ['，', ',', ' ', '、', '的']:
                        pos = part.rfind(sep, max_chars_per_line - 4, max_chars_per_line + 4)
                        if pos > 0:
                            mid = pos + 1
                            break
                    subtitles.append(part[:mid].strip() + '\n' + part[mid:].strip())
                    remaining = remaining[max_chars:]

    char_counts = [len(s.replace('\n', '')) for s in subtitles]
    total_chars = sum(char_counts) or 1
    min_slot = 0.6

    blocks = []
    current_time = 0.0
    for index, (sub, chars) in enumerate(zip(subtitles, char_counts)):
        slot_duration = max(min_slot, (chars / total_chars) * duration * 0.95)
        start = current_time
        end = min(duration, current_time + slot_duration)
        if index == len(subtitles) - 1:
            end = duration
        current_time = end
        blocks.append(f"{index + 1}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{sub}\n")

    target.write_text("\n".join(blocks), encoding="utf-8")


def _extract_audio(video_path: Path) -> Path:
    """Extract 16kHz mono WAV audio from video for whisper."""
    audio_path = video_path.parent / "audio.wav"
    result = subprocess.run(
        [_ffmpeg_path(), "-y", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", str(audio_path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"音频提取失败: {result.stderr[-500:]}")
    return audio_path


def _whisper_srt(video_path: Path, duration: float, target: Path, max_chars: int = 28) -> dict:
    """Run whisper on video audio and generate word-timestamped SRT.
    Returns {'ok': bool, 'text': str, 'language': str, ...}
    """
    import whisper

    audio_path = _extract_audio(video_path)
    model_size = os.getenv("WHISPER_MODEL", "tiny")
    model = whisper.load_model(model_size)

    result = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        language=None,  # auto-detect
        verbose=False,
    )

    words = []
    for segment in result.get("segments", []):
        for w in segment.get("words", []):
            word_text = w.get("word", "").strip()
            if word_text:
                words.append({
                    "word": word_text,
                    "start": w.get("start", 0),
                    "end": w.get("end", 0),
                })

    if not words:
        return {"ok": False, "reason": "whisper 未识别出任何词汇", "language": result.get("language", "unknown")}

    # Group words into subtitle lines
    lang = result.get("language", "en")
    is_cjk = lang in ("zh", "ja", "ko")
    max_chars_per_line = max_chars // 2  # 14 for 2-line subtitles

    subtitles = []  # [(start, end, text)]
    buffer_words = []
    buffer_chars = 0
    buffer_start = words[0]["start"]

    for w in words:
        w_len = 1 if is_cjk else len(w["word"]) + 1  # +1 for space
        if buffer_chars + w_len > max_chars:
            # Flush current buffer
            if buffer_words:
                text = "".join(b["word"] for b in buffer_words) if is_cjk else " ".join(b["word"] for b in buffer_words)
                # Split into 2 lines if needed
                if len(text.replace(" ", "")) > max_chars_per_line:
                    mid = len(text) // 2
                    if not is_cjk:
                        words_list = text.split()
                        mid_idx = len(words_list) // 2
                        line1 = " ".join(words_list[:mid_idx])
                        line2 = " ".join(words_list[mid_idx:])
                        text = f"{line1}\n{line2}"
                    else:
                        for sep in ['，', ',', ' ', '、']:
                            pos = text.rfind(sep, mid - 4, mid + 4)
                            if pos > 0:
                                text = f"{text[:pos+1].strip()}\n{text[pos+1:].strip()}"
                                break
                        else:
                            text = f"{text[:mid]}\n{text[mid:]}"
                subtitles.append((buffer_start, buffer_words[-1]["end"], text))
            buffer_words = [w]
            buffer_chars = w_len
            buffer_start = w["start"]
        else:
            buffer_words.append(w)
            buffer_chars += w_len

    # Flush remaining
    if buffer_words:
        text = "".join(b["word"] for b in buffer_words) if is_cjk else " ".join(b["word"] for b in buffer_words)
        subtitles.append((buffer_start, buffer_words[-1]["end"], text))

    # Write SRT
    blocks = []
    for i, (start, end, text) in enumerate(subtitles):
        blocks.append(f"{i + 1}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{text}\n")
    target.write_text("\n".join(blocks), encoding="utf-8")

    # Cleanup audio temp file
    try:
        audio_path.unlink()
    except OSError:
        pass

    return {
        "ok": True,
        "text": result.get("text", ""),
        "language": lang,
        "subtitle_count": len(subtitles),
        "model": model_size,
    }


def align_subtitles(payload: dict, output_directory: Path) -> dict:
    """Run whisper on video audio and return word-timestamped subtitles.
    Uses whisper's OWN transcription (not force-aligned to script),
    because generated videos may not follow the original script word-for-word."""
    import whisper

    source_url = str(payload.get("source_video_url") or "").strip()
    script_text = str(payload.get("script_text") or payload.get("subtitle_text") or "").strip()
    if not source_url:
        raise ValueError("缺少视频地址")

    with tempfile.TemporaryDirectory(prefix="adflow-align-") as temp:
        temp_path = Path(temp)
        source_path = temp_path / "source.mp4"
        _download(source_url, source_path)

        audio_path = _extract_audio(source_path)
        model_size = os.getenv("WHISPER_MODEL", "tiny")
        model = whisper.load_model(model_size)

        result = model.transcribe(str(audio_path), word_timestamps=True, language=None, verbose=False)

        whisper_words = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                word_text = w.get("word", "").strip()
                if word_text:
                    whisper_words.append({"word": word_text, "start": w.get("start", 0), "end": w.get("end", 0)})

        if not whisper_words:
            raise RuntimeError("whisper 未识别出任何词汇")

        lang = result.get("language", "en")
        is_cjk = lang in ("zh", "ja", "ko")
        whisper_text = " ".join(w["word"] for w in whisper_words)

        # Group whisper words into subtitle-sized chunks
        max_chars, max_line = 28, 14
        subtitles = []
        buf_words, buf_chars, buf_start = [], 0, whisper_words[0]["start"]

        for w in whisper_words:
            w_len = 1 if is_cjk else len(w["word"]) + 1
            if buf_chars + w_len > max_chars:
                if buf_words:
                    text = ("".join(b["word"] for b in buf_words) if is_cjk
                            else " ".join(b["word"] for b in buf_words))
                    clean_len = len(text.replace(" ", ""))
                    if clean_len > max_line:
                        mid = len(text) // 2
                        if not is_cjk:
                            wl = text.split(); mi = len(wl) // 2
                            text = f"{' '.join(wl[:mi])}\n{' '.join(wl[mi:])}"
                        else:
                            for sep in ['，', ',', ' ']:
                                p = text.rfind(sep, mid - 3, mid + 3)
                                if p > 0:
                                    text = f"{text[:p+1].strip()}\n{text[p+1:].strip()}"; break
                            else:
                                text = f"{text[:mid]}\n{text[mid:]}"
                    subtitles.append((buf_start, buf_words[-1]["end"], text))
                buf_words, buf_chars, buf_start = [w], w_len, w["start"]
            else:
                buf_words.append(w); buf_chars += w_len

        if buf_words:
            text = "".join(b["word"] for b in buf_words) if is_cjk else " ".join(b["word"] for b in buf_words)
            subtitles.append((buf_start, buf_words[-1]["end"], text))

        srt_path = temp_path / "captions.srt"
        blocks = [f"{i+1}\n{_srt_timestamp(s)} --> {_srt_timestamp(e)}\n{t}\n" for i, (s, e, t) in enumerate(subtitles)]
        srt_path.write_text("\n".join(blocks), encoding="utf-8")

        output_directory.mkdir(parents=True, exist_ok=True)
        output_name = f"aligned-{uuid.uuid4().hex[:12]}.srt"
        output_path = output_directory / output_name
        output_path.write_text(srt_path.read_text(), encoding="utf-8")

    return {
        "ok": True, "language": lang,
        "whisper_text": whisper_text, "subtitle_count": len(subtitles),
        "srt_url": f"/generated/edits/{output_name}",
        "subtitles": [{"start": s, "end": e, "text": t} for s, e, t in subtitles],
    }


def render_edit(payload: dict, output_directory: Path) -> dict:
    source_url = str(payload.get("source_video_url") or "").strip()
    if not source_url:
        raise ValueError("缺少待剪辑视频")
    output_directory.mkdir(parents=True, exist_ok=True)
    output_name = f"adflow-edit-{uuid.uuid4().hex[:12]}.mp4"
    output_path = output_directory / output_name

    with tempfile.TemporaryDirectory(prefix="adflow-edit-") as temp:
        temp_path = Path(temp)
        source_path = temp_path / "source.mp4"
        _download(source_url, source_path)
        source_duration = _duration(source_path)
        source_has_audio = _has_audio(source_path)
        trim_start = max(0.0, float(payload.get("trim_start") or 0))
        trim_end = float(payload.get("trim_end") or 0)
        duration = max(0.5, (trim_end - trim_start) if trim_end > trim_start else source_duration - trim_start)

        command = [_ffmpeg_path(), "-y", "-ss", str(trim_start), "-t", str(duration), "-i", str(source_path)]
        music_value = str(payload.get("music_data_url") or "")
        if music_value:
            music_path = temp_path / "music"
            _decode_data_url(music_value, music_path)
            command += ["-stream_loop", "-1", "-i", str(music_path)]

        filters = []
        aspect = str(payload.get("output_aspect") or "source")
        if aspect == "9:16":
            filters.append("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920")
        elif aspect == "16:9":
            filters.append("scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080")
        elif aspect == "1:1":
            filters.append("scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080")

        subtitle_text = str(payload.get("subtitle_text") or "").strip()
        if payload.get("subtitles_enabled") and subtitle_text:
            subtitle_path = temp_path / "captions.srt"
            use_whisper = bool(payload.get("use_whisper"))
            if use_whisper:
                whisper_result = _whisper_srt(source_path, duration, subtitle_path)
                if not whisper_result.get("ok"):
                    # Fallback to proportional method if whisper fails
                    _write_srt(subtitle_text, duration, subtitle_path)
            else:
                _write_srt(subtitle_text, duration, subtitle_path)
            escaped = str(subtitle_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
            filters.append(
                f"subtitles='{escaped}':force_style='FontName=Arial,FontSize=14,Alignment=2,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=3,Outline=1,MarginV=48'"
            )
        if filters:
            command += ["-vf", ",".join(filters)]

        if music_value:
            volume = min(1.0, max(0.0, float(payload.get("music_volume") or 0.2)))
            if source_has_audio:
                audio_filter = (
                    f"[1:a]volume={volume}[music];"
                    "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                )
            else:
                audio_filter = f"[1:a]volume={volume}[aout]"
            command += ["-filter_complex", audio_filter, "-map", "0:v:0", "-map", "[aout]"]
        else:
            command += ["-map", "0:v:0"]
            if not payload.get("no_voice"):
                command += ["-map", "0:a?"]
        command += [
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(output_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-2000:] or "FFmpeg 剪辑失败")

        # Upscale (FFmpeg lanczos - free, instant)
        enhance = payload.get("enhance")
        if enhance:
            target_h = {"1080p": 1080, "2k": 1440, "4k": 2160}.get(
                str(enhance).lower(), 1080
            )
            upscaled = temp_path / "upscaled.mp4"
            upscale_video(output_path, upscaled, target_h)
            output_path = upscaled

    return {
        "ok": True,
        "output_url": f"/generated/edits/{output_name}",
        "duration": round(duration, 2),
        "file_name": output_name,
    }


def upscale_video(input_path: Path, output_path: Path, target_height: int = 1080) -> dict:
    """Upscale video using FFmpeg lanczos (free, instant)."""
    result = subprocess.run(
        [_ffmpeg_path(), "-y", "-i", str(input_path),
         "-vf", f"scale=-2:{target_height}:flags=lanczos",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
         str(output_path)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-500:] or "画质增强失败")
    return {"ok": True, "method": "lanczos", "target_height": target_height}


def upscale_video_ai(input_path: Path, output_path: Path, target_height: int = 1080) -> dict:
    """AI upscale using Real-ESRGAN (local, free).
    Extracts frames → upscales each → reassembles with audio."""
    binary = os.getenv("REALESRGAN_PATH", "").strip() or shutil.which("realesrgan-ncnn-vulkan")
    models = os.getenv("REALESRGAN_MODELS", "").strip()
    if not binary:
        raise RuntimeError("找不到 Real-ESRGAN，请设置 REALESRGAN_PATH")
    if not models or not Path(models).is_dir():
        raise RuntimeError("找不到 Real-ESRGAN 模型目录，请设置 REALESRGAN_MODELS")

    with tempfile.TemporaryDirectory(prefix="adflow-esrgan-") as temp:
        temp_path = Path(temp)
        frames_dir = temp_path / "frames"
        upscaled_dir = temp_path / "upscaled"
        frames_dir.mkdir()
        upscaled_dir.mkdir()

        # Extract frames
        subprocess.run(
            [_ffmpeg_path(), "-y", "-i", str(input_path), "-q:v", "1",
             str(frames_dir / "frame_%05d.png")],
            capture_output=True, text=True, check=True,
        )

        # Upscale each frame with Real-ESRGAN
        frame_files = sorted(frames_dir.glob("frame_*.png"))
        if not frame_files:
            raise RuntimeError("未提取到视频帧")

        for frame in frame_files:
            out_frame = upscaled_dir / frame.name
            subprocess.run(
                [binary, "-i", str(frame), "-o", str(out_frame),
                 "-m", models, "-n", "realesrgan-x4plus", "-s", "2"],
                capture_output=True, text=True, check=True,
                timeout=30,
            )

        # Get original FPS and reassemble with audio
        fps_result = subprocess.run(
            [_ffmpeg_path(), "-i", str(input_path)],
            capture_output=True, text=True, check=False,
        )
        import re as _re
        fps_match = _re.search(r'(\d+(?:\.\d+)?)\s*(?:fps|FPS)', fps_result.stderr)
        fps = fps_match.group(1) if fps_match else "30"

        subprocess.run(
            [_ffmpeg_path(), "-y", "-framerate", fps, "-i",
             str(upscaled_dir / "frame_%05d.png"),
             "-i", str(input_path),
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-c:a", "aac", "-b:a", "192k", "-map", "0:v:0", "-map", "1:a:0?",
             "-shortest", "-movflags", "+faststart", str(output_path)],
            capture_output=True, text=True, check=True,
        )
    return {"ok": True, "method": "realesrgan", "target_height": target_height}


def export_editing_handoff(payload: dict, output_directory: Path, target: str) -> dict:
    """Create an honest portable handoff instead of pretending to write proprietary projects."""
    source_url = str(payload.get("source_video_url") or "").strip()
    if not source_url:
        raise ValueError("缺少待交付视频")
    output_directory.mkdir(parents=True, exist_ok=True)
    handoff_id = uuid.uuid4().hex[:12]
    manifest = {
        "schema": "dahai-aigc-edit-handoff/v1",
        "target": target,
        "source_video": "source.mp4",
        "trim": {"start": payload.get("trim_start") or 0, "end": payload.get("trim_end") or None},
        "output_aspect": payload.get("output_aspect") or "source",
        "music": {"file": "music.bin" if payload.get("music_data_url") else None, "volume": payload.get("music_volume") or 0.2},
        "subtitles": {"file": "captions.srt" if payload.get("subtitle_text") else None},
        "creative_context": payload.get("creative_context") or {},
        "instructions": (
            "将素材导入剪映后按 manifest.json 完成剪辑。"
            if target == "jianying" else
            "在 ChatCut 项目中导入素材，并按 manifest.json 继续精剪、转写和导出。"
        ),
    }
    archive_name = f"{target}-handoff-{handoff_id}.zip"
    archive_path = output_directory / archive_name
    with tempfile.TemporaryDirectory(prefix=f"{target}-handoff-") as temp:
        temp_path = Path(temp)
        source_path = temp_path / "source.mp4"
        _download(source_url, source_path)
        subtitle_text = str(payload.get("subtitle_text") or "").strip()
        if subtitle_text:
            _write_srt(subtitle_text, _duration(source_path), temp_path / "captions.srt")
        if payload.get("music_data_url"):
            _decode_data_url(str(payload["music_data_url"]), temp_path / "music.bin")
        (temp_path / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in temp_path.iterdir():
                archive.write(item, item.name)
    return {"ok": True, "target": target, "output_url": f"/generated/edits/{archive_name}", "file_name": archive_name}
