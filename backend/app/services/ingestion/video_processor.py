# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# process_video(video_bytes: bytes, filename: str) -> ProcessedAsset
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import httpx
import structlog

from app.services.ingestion.vision_processor import process_image

logger = structlog.get_logger()

FRAME_INTERVAL_SECONDS = 30


async def _transcribe_audio(audio_path: str) -> str:
    """Transcribe audio using Whisper API (OpenAI or Groq)."""
    api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    base_url = "https://api.groq.com/openai/v1" if os.environ.get("GROQ_API_KEY") else "https://api.openai.com/v1"
    model = "whisper-large-v3" if os.environ.get("GROQ_API_KEY") else "whisper-1"

    async with httpx.AsyncClient(timeout=300) as client:
        with open(audio_path, "rb") as f:
            response = await client.post(
                f"{base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (Path(audio_path).name, f, "audio/wav")},
                data={"model": model},
            )
            response.raise_for_status()
            return response.json().get("text", "")


def _extract_audio(video_path: str, output_path: str) -> bool:
    """Extract audio track from video using ffmpeg."""
    result = subprocess.run(
        ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", output_path, "-y"],
        capture_output=True,
    )
    return result.returncode == 0


def _extract_frames(video_path: str, output_dir: str, interval: int = FRAME_INTERVAL_SECONDS) -> list[str]:
    """Extract key frames from video at regular intervals."""
    subprocess.run(
        ["ffmpeg", "-i", video_path, "-vf", f"fps=1/{interval}",
         f"{output_dir}/frame_%04d.jpg", "-y"],
        capture_output=True,
    )
    frames = sorted(Path(output_dir).glob("frame_*.jpg"))
    return [str(f) for f in frames]


async def process_video(video_bytes: bytes, filename: str) -> dict:
    """Process video: transcribe audio + sample frames for vision analysis."""
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, filename)
        audio_path = os.path.join(tmpdir, "audio.wav")

        with open(video_path, "wb") as f:
            f.write(video_bytes)

        parts: list[str] = []

        # 1. Transcribe audio
        has_audio = _extract_audio(video_path, audio_path)
        if has_audio and os.path.exists(audio_path):
            try:
                transcript = await _transcribe_audio(audio_path)
                if transcript:
                    parts.append(f"## Audio Transcript\n\n{transcript}")
            except Exception as e:
                logger.warning("whisper_failed", error=str(e))
                parts.append("## Audio Transcript\n\n[Transcription unavailable]")

        # 2. Sample key frames
        frame_paths = _extract_frames(video_path, tmpdir)
        if frame_paths:
            parts.append("\n## Key Frame Descriptions\n")
            for i, frame_path in enumerate(frame_paths[:10]):  # max 10 frames
                try:
                    frame_bytes = Path(frame_path).read_bytes()
                    result = await process_image(frame_bytes, f"frame_{i}.jpg")
                    timestamp = i * FRAME_INTERVAL_SECONDS
                    parts.append(f"### Frame at {timestamp}s\n{result['extracted_text']}\n")
                except Exception as e:
                    logger.warning("frame_processing_failed", frame=i, error=str(e))

        combined = "\n\n".join(parts) if parts else "No content could be extracted from this video."

        # Get video duration
        duration = 0
        try:
            probe = subprocess.run(
                ["ffmpeg", "-i", video_path, "-f", "null", "-"],
                capture_output=True, text=True,
            )
            # Parse duration from stderr
            for line in probe.stderr.split("\n"):
                if "Duration:" in line:
                    time_str = line.split("Duration:")[1].split(",")[0].strip()
                    h, m, s = time_str.split(":")
                    duration = int(h) * 3600 + int(m) * 60 + float(s)
                    break
        except Exception:
            pass

        logger.info("video_processed", filename=filename, duration=duration, frames=len(frame_paths))
        return {
            "extracted_text": combined,
            "metadata": {
                "duration_seconds": duration,
                "frames_sampled": len(frame_paths),
                "has_audio": has_audio,
                "file_size": len(video_bytes),
            },
        }
