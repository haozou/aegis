"""Video processing tools powered by ffmpeg."""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import tempfile
import uuid
from typing import Any

from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)

VIDEO_TIMEOUT = 600  # 10 minutes for video operations
MAX_OUTPUT_BYTES = 102400  # 100KB for ffmpeg logs


async def _run_ffmpeg(
    args: list[str],
    cwd: str | None = None,
    timeout: int = VIDEO_TIMEOUT,
) -> tuple[int, str]:
    """Run an ffmpeg/ffprobe command and return (returncode, output)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return -1, f"Command timed out after {timeout}s"

        output = stdout.decode("utf-8", errors="replace")
        if len(output.encode()) > MAX_OUTPUT_BYTES:
            output = output[: MAX_OUTPUT_BYTES // 4]
            output += "\n... [output truncated]"

        return proc.returncode or 0, output
    except FileNotFoundError as e:
        return -1, f"Command not found: {e}. Make sure ffmpeg is installed."
    except Exception as e:
        return -1, f"Execution error: {e}"


def _sandbox_path(context: ToolContext, filename: str) -> str:
    """Return an absolute path inside the sandbox."""
    base = pathlib.Path(context.sandbox_path or "data/sandbox")
    base.mkdir(parents=True, exist_ok=True)
    # If the filename already looks absolute and is under sandbox, allow it
    p = pathlib.Path(filename)
    if p.is_absolute():
        return str(p)
    return str(base / filename)


def _output_name(prefix: str, ext: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"


# ---------------------------------------------------------------------------
# video_probe
# ---------------------------------------------------------------------------


class VideoProbe(BaseTool):
    """Probe a video file and return metadata (streams, duration, codec, etc.)."""

    @property
    def name(self) -> str:
        return "video_probe"

    @property
    def description(self) -> str:
        return (
            "Inspect a video or audio file and return detailed metadata: "
            "streams, codec names, duration, resolution, frame rate, bitrate, etc. "
            "The file must exist on the sandbox filesystem. "
            "Use this before any editing operation to understand the file."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Path to the input video/audio file (relative to sandbox or absolute).",
                },
            },
            "required": ["input_file"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        input_file = _sandbox_path(context, kwargs["input_file"])

        if not os.path.exists(input_file):
            return ToolResult(
                output=f"File not found: {input_file}", is_error=True
            )

        args = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            input_file,
        ]
        rc, output = await _run_ffmpeg(args, timeout=30)
        if rc != 0:
            return ToolResult(output=f"ffprobe failed:\n{output}", is_error=True)

        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return ToolResult(output=output, metadata={"raw": True})

        # Build a concise summary
        fmt = data.get("format", {})
        streams = data.get("streams", [])
        summary_lines = [
            f"File: {os.path.basename(input_file)}",
            f"Duration: {fmt.get('duration', 'unknown')}s",
            f"Size: {fmt.get('size', 'unknown')} bytes",
            f"Bitrate: {fmt.get('bit_rate', 'unknown')} bps",
            f"Format: {fmt.get('format_long_name', fmt.get('format_name', 'unknown'))}",
            "",
            f"Streams ({len(streams)}):",
        ]
        for s in streams:
            codec_type = s.get("codec_type", "?")
            codec_name = s.get("codec_name", "?")
            if codec_type == "video":
                w, h = s.get("width", "?"), s.get("height", "?")
                fps = s.get("r_frame_rate", "?")
                summary_lines.append(
                    f"  [{s.get('index')}] video: {codec_name} {w}x{h} @ {fps} fps"
                )
            elif codec_type == "audio":
                sr = s.get("sample_rate", "?")
                ch = s.get("channels", "?")
                summary_lines.append(
                    f"  [{s.get('index')}] audio: {codec_name} {sr}Hz {ch}ch"
                )
            else:
                summary_lines.append(f"  [{s.get('index')}] {codec_type}: {codec_name}")

        return ToolResult(
            output="\n".join(summary_lines),
            metadata=data,
        )


# ---------------------------------------------------------------------------
# video_cut
# ---------------------------------------------------------------------------


class VideoCut(BaseTool):
    """Cut a segment from a video file."""

    @property
    def name(self) -> str:
        return "video_cut"

    @property
    def description(self) -> str:
        return (
            "Cut a time segment from a video file. "
            "Uses stream-copy for fast, lossless cutting (no re-encoding). "
            "Output file is saved in the sandbox. "
            "Times can be in seconds (e.g. 30.5) or HH:MM:SS format (e.g. 00:01:30)."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Path to the input video file.",
                },
                "start_time": {
                    "type": "string",
                    "description": "Start time (seconds or HH:MM:SS). Default: beginning of file.",
                    "default": "0",
                },
                "end_time": {
                    "type": "string",
                    "description": "End time (seconds or HH:MM:SS). Omit or leave empty to cut to end.",
                },
                "output_file": {
                    "type": "string",
                    "description": "Output filename (optional; auto-generated if omitted).",
                },
                "reencode": {
                    "type": "boolean",
                    "description": "Re-encode instead of stream-copy for frame-accurate cuts. Slower but more precise.",
                    "default": False,
                },
            },
            "required": ["input_file", "start_time"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        input_file = _sandbox_path(context, kwargs["input_file"])
        start_time = str(kwargs.get("start_time", "0"))
        end_time = kwargs.get("end_time", "")
        reencode = bool(kwargs.get("reencode", False))

        if not os.path.exists(input_file):
            return ToolResult(output=f"File not found: {input_file}", is_error=True)

        ext = pathlib.Path(input_file).suffix.lstrip(".") or "mp4"
        out_name = kwargs.get("output_file") or _output_name("cut", ext)
        output_file = _sandbox_path(context, out_name)

        args = ["ffmpeg", "-y", "-i", input_file, "-ss", start_time]
        if end_time:
            args += ["-to", end_time]
        if reencode:
            args += ["-c:v", "libx264", "-c:a", "aac", "-preset", "fast"]
        else:
            args += ["-c", "copy"]
        args.append(output_file)

        rc, output = await _run_ffmpeg(args, cwd=context.sandbox_path, timeout=VIDEO_TIMEOUT)
        if rc != 0:
            return ToolResult(output=f"video_cut failed:\n{output}", is_error=True)

        size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        return ToolResult(
            output=f"Cut saved to: {out_name}\nSize: {size} bytes",
            metadata={"output_file": out_name, "output_path": output_file, "size": size},
        )


# ---------------------------------------------------------------------------
# video_concat
# ---------------------------------------------------------------------------


class VideoConcat(BaseTool):
    """Concatenate multiple video clips into one file."""

    @property
    def name(self) -> str:
        return "video_concat"

    @property
    def description(self) -> str:
        return (
            "Concatenate two or more video files into a single output file. "
            "All input files must have identical codec, resolution, and frame rate "
            "(use video_export to normalise them first if needed). "
            "Uses the ffmpeg concat demuxer for lossless joining."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of video file paths to concatenate.",
                    "minItems": 2,
                },
                "output_file": {
                    "type": "string",
                    "description": "Output filename (optional; auto-generated if omitted).",
                },
            },
            "required": ["input_files"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        input_files = kwargs["input_files"]
        if len(input_files) < 2:
            return ToolResult(output="Need at least 2 input files.", is_error=True)

        resolved = []
        for f in input_files:
            p = _sandbox_path(context, f)
            if not os.path.exists(p):
                return ToolResult(output=f"File not found: {p}", is_error=True)
            resolved.append(p)

        ext = pathlib.Path(resolved[0]).suffix.lstrip(".") or "mp4"
        out_name = kwargs.get("output_file") or _output_name("concat", ext)
        output_file = _sandbox_path(context, out_name)

        # Write concat list file
        sandbox = pathlib.Path(context.sandbox_path or "data/sandbox")
        list_path = sandbox / f"concat_list_{uuid.uuid4().hex[:8]}.txt"
        with open(list_path, "w") as fh:
            for p in resolved:
                fh.write(f"file '{p}'\n")

        args = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_path),
            "-c", "copy",
            output_file,
        ]
        rc, output = await _run_ffmpeg(args, cwd=context.sandbox_path, timeout=VIDEO_TIMEOUT)

        # Clean up list file
        try:
            list_path.unlink()
        except Exception:
            pass

        if rc != 0:
            return ToolResult(output=f"video_concat failed:\n{output}", is_error=True)

        size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        return ToolResult(
            output=f"Concatenated {len(resolved)} files → {out_name}\nSize: {size} bytes",
            metadata={"output_file": out_name, "output_path": output_file, "size": size, "input_count": len(resolved)},
        )


# ---------------------------------------------------------------------------
# video_add_audio
# ---------------------------------------------------------------------------


class VideoAddAudio(BaseTool):
    """Replace or mix audio track in a video file."""

    @property
    def name(self) -> str:
        return "video_add_audio"

    @property
    def description(self) -> str:
        return (
            "Add, replace, or mix an audio track into a video file. "
            "Can replace the existing audio, mix it with background music, "
            "or add audio to a silent video. "
            "Audio is re-encoded to AAC; video is stream-copied."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "video_file": {
                    "type": "string",
                    "description": "Path to the video file.",
                },
                "audio_file": {
                    "type": "string",
                    "description": "Path to the audio file (MP3, WAV, AAC, etc.).",
                },
                "mode": {
                    "type": "string",
                    "enum": ["replace", "mix"],
                    "description": "'replace' discards the original audio and uses the new one. 'mix' blends both tracks.",
                    "default": "replace",
                },
                "audio_volume": {
                    "type": "number",
                    "description": "Volume multiplier for the new audio track (1.0 = original, 0.5 = half). Default: 1.0",
                    "default": 1.0,
                },
                "original_volume": {
                    "type": "number",
                    "description": "Volume multiplier for the original video audio when mode=mix. Default: 1.0",
                    "default": 1.0,
                },
                "output_file": {
                    "type": "string",
                    "description": "Output filename (optional).",
                },
            },
            "required": ["video_file", "audio_file"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        video_file = _sandbox_path(context, kwargs["video_file"])
        audio_file = _sandbox_path(context, kwargs["audio_file"])
        mode = kwargs.get("mode", "replace")
        audio_vol = float(kwargs.get("audio_volume", 1.0))
        orig_vol = float(kwargs.get("original_volume", 1.0))

        for path, label in [(video_file, "video_file"), (audio_file, "audio_file")]:
            if not os.path.exists(path):
                return ToolResult(output=f"File not found ({label}): {path}", is_error=True)

        ext = pathlib.Path(video_file).suffix.lstrip(".") or "mp4"
        out_name = kwargs.get("output_file") or _output_name("audio", ext)
        output_file = _sandbox_path(context, out_name)

        if mode == "replace":
            args = [
                "ffmpeg", "-y",
                "-i", video_file,
                "-i", audio_file,
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-af", f"volume={audio_vol}",
                "-shortest",
                output_file,
            ]
        else:
            # mix mode — use amix filter
            args = [
                "ffmpeg", "-y",
                "-i", video_file,
                "-i", audio_file,
                "-filter_complex",
                f"[0:a]volume={orig_vol}[a0];[1:a]volume={audio_vol}[a1];[a0][a1]amix=inputs=2:duration=first[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                output_file,
            ]

        rc, output = await _run_ffmpeg(args, cwd=context.sandbox_path, timeout=VIDEO_TIMEOUT)
        if rc != 0:
            return ToolResult(output=f"video_add_audio failed:\n{output}", is_error=True)

        size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        return ToolResult(
            output=f"Audio {mode}d → {out_name}\nSize: {size} bytes",
            metadata={"output_file": out_name, "output_path": output_file, "size": size, "mode": mode},
        )


# ---------------------------------------------------------------------------
# video_thumbnail
# ---------------------------------------------------------------------------


class VideoThumbnail(BaseTool):
    """Extract a thumbnail image from a video at a specific timestamp."""

    @property
    def name(self) -> str:
        return "video_thumbnail"

    @property
    def description(self) -> str:
        return (
            "Extract a single frame from a video as a JPEG thumbnail. "
            "Useful for previewing content or generating cover images."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Path to the video file.",
                },
                "timestamp": {
                    "type": "string",
                    "description": "Timestamp to capture (seconds or HH:MM:SS). Default: 0 (first frame).",
                    "default": "0",
                },
                "width": {
                    "type": "integer",
                    "description": "Thumbnail width in pixels. Height is scaled proportionally. Default: 640.",
                    "default": 640,
                },
                "output_file": {
                    "type": "string",
                    "description": "Output filename (optional; .jpg extension).",
                },
            },
            "required": ["input_file"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        input_file = _sandbox_path(context, kwargs["input_file"])
        timestamp = str(kwargs.get("timestamp", "0"))
        width = int(kwargs.get("width", 640))

        if not os.path.exists(input_file):
            return ToolResult(output=f"File not found: {input_file}", is_error=True)

        out_name = kwargs.get("output_file") or _output_name("thumb", "jpg")
        output_file = _sandbox_path(context, out_name)

        args = [
            "ffmpeg", "-y",
            "-ss", timestamp,
            "-i", input_file,
            "-vframes", "1",
            "-vf", f"scale={width}:-1",
            "-q:v", "2",
            output_file,
        ]
        rc, output = await _run_ffmpeg(args, cwd=context.sandbox_path, timeout=60)
        if rc != 0:
            return ToolResult(output=f"video_thumbnail failed:\n{output}", is_error=True)

        size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        return ToolResult(
            output=f"Thumbnail saved to: {out_name}\nSize: {size} bytes",
            metadata={"output_file": out_name, "output_path": output_file, "size": size},
        )


# ---------------------------------------------------------------------------
# video_export
# ---------------------------------------------------------------------------


class VideoExport(BaseTool):
    """Transcode / export a video with custom resolution, format, codec, and bitrate."""

    @property
    def name(self) -> str:
        return "video_export"

    @property
    def description(self) -> str:
        return (
            "Transcode a video to a different format, resolution, or codec. "
            "Use this to normalise clips before concatenation, compress for web delivery, "
            "or convert between formats (MP4, MKV, MOV, WebM, GIF, etc.). "
            "Supports H.264, H.265/HEVC, VP9, AV1, and GIF output."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Path to the input video file.",
                },
                "output_file": {
                    "type": "string",
                    "description": "Output filename including extension (e.g. output.mp4, clip.webm, animation.gif).",
                },
                "video_codec": {
                    "type": "string",
                    "enum": ["h264", "h265", "vp9", "av1", "gif", "copy"],
                    "description": "Output video codec. 'copy' for lossless passthrough. Default: h264.",
                    "default": "h264",
                },
                "audio_codec": {
                    "type": "string",
                    "enum": ["aac", "mp3", "opus", "copy", "none"],
                    "description": "Output audio codec. 'none' strips audio. Default: aac.",
                    "default": "aac",
                },
                "width": {
                    "type": "integer",
                    "description": "Output width in pixels. Height is scaled proportionally (maintains aspect ratio). Omit to keep original.",
                },
                "height": {
                    "type": "integer",
                    "description": "Output height in pixels. Omit to keep original.",
                },
                "video_bitrate": {
                    "type": "string",
                    "description": "Target video bitrate (e.g. '2M', '500k'). Omit for default.",
                },
                "audio_bitrate": {
                    "type": "string",
                    "description": "Target audio bitrate (e.g. '128k', '192k'). Omit for default.",
                },
                "fps": {
                    "type": "number",
                    "description": "Output frame rate (e.g. 24, 30, 60). Omit to keep original.",
                },
                "preset": {
                    "type": "string",
                    "enum": ["ultrafast", "fast", "medium", "slow", "veryslow"],
                    "description": "Encoding speed vs compression tradeoff (h264/h265 only). Default: fast.",
                    "default": "fast",
                },
                "crf": {
                    "type": "integer",
                    "description": "Constant Rate Factor (quality). Lower = better quality, larger file. 0-51 for h264 (18-28 typical). Omit to use bitrate instead.",
                },
            },
            "required": ["input_file", "output_file"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        input_file = _sandbox_path(context, kwargs["input_file"])
        out_name = kwargs["output_file"]
        output_file = _sandbox_path(context, out_name)

        if not os.path.exists(input_file):
            return ToolResult(output=f"File not found: {input_file}", is_error=True)

        video_codec = kwargs.get("video_codec", "h264")
        audio_codec = kwargs.get("audio_codec", "aac")
        width = kwargs.get("width")
        height = kwargs.get("height")
        video_bitrate = kwargs.get("video_bitrate")
        audio_bitrate = kwargs.get("audio_bitrate")
        fps = kwargs.get("fps")
        preset = kwargs.get("preset", "fast")
        crf = kwargs.get("crf")

        # Map codec names to ffmpeg encoder names
        codec_map = {
            "h264": "libx264",
            "h265": "libx265",
            "vp9": "libvpx-vp9",
            "av1": "libaom-av1",
            "gif": "gif",
            "copy": "copy",
        }
        audio_codec_map = {
            "aac": "aac",
            "mp3": "libmp3lame",
            "opus": "libopus",
            "copy": "copy",
            "none": None,
        }

        args = ["ffmpeg", "-y", "-i", input_file]

        # Video filters (scale / fps)
        vf_parts = []
        if width and height:
            vf_parts.append(f"scale={width}:{height}")
        elif width:
            vf_parts.append(f"scale={width}:-2")
        elif height:
            vf_parts.append(f"scale=-2:{height}")
        if fps:
            vf_parts.append(f"fps={fps}")
        if vf_parts and video_codec != "gif":
            args += ["-vf", ",".join(vf_parts)]

        # GIF special handling
        if video_codec == "gif":
            palette_name = _output_name("palette", "png")
            palette_file = _sandbox_path(context, palette_name)
            scale_filter = f"scale={width}:-1:flags=lanczos" if width else "scale=320:-1:flags=lanczos"
            # Step 1: generate palette
            palette_args = [
                "ffmpeg", "-y", "-i", input_file,
                "-vf", f"{scale_filter},palettegen",
                palette_file,
            ]
            rc, out = await _run_ffmpeg(palette_args, timeout=120)
            if rc != 0:
                return ToolResult(output=f"GIF palette generation failed:\n{out}", is_error=True)
            # Step 2: apply palette
            fps_filter = f"fps={fps}," if fps else "fps=15,"
            args = [
                "ffmpeg", "-y", "-i", input_file, "-i", palette_file,
                "-lavfi", f"{fps_filter}{scale_filter}[x];[x][1:v]paletteuse",
                output_file,
            ]
            rc, output = await _run_ffmpeg(args, cwd=context.sandbox_path, timeout=VIDEO_TIMEOUT)
            try:
                pathlib.Path(palette_file).unlink()
            except Exception:
                pass
            if rc != 0:
                return ToolResult(output=f"video_export (GIF) failed:\n{output}", is_error=True)
            size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
            return ToolResult(
                output=f"GIF exported → {out_name}\nSize: {size} bytes",
                metadata={"output_file": out_name, "output_path": output_file, "size": size},
            )

        # Video codec
        enc = codec_map.get(video_codec, "libx264")
        args += ["-c:v", enc]
        if enc not in ("copy", "gif") and preset:
            args += ["-preset", preset]
        if crf is not None and enc not in ("copy", "gif"):
            args += ["-crf", str(crf)]
        elif video_bitrate:
            args += ["-b:v", video_bitrate]

        # Audio codec
        aenc = audio_codec_map.get(audio_codec, "aac")
        if aenc is None:
            args += ["-an"]  # no audio
        else:
            args += ["-c:a", aenc]
            if audio_bitrate:
                args += ["-b:a", audio_bitrate]

        args.append(output_file)

        rc, output = await _run_ffmpeg(args, cwd=context.sandbox_path, timeout=VIDEO_TIMEOUT)
        if rc != 0:
            return ToolResult(output=f"video_export failed:\n{output}", is_error=True)

        size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        return ToolResult(
            output=f"Exported → {out_name}\nSize: {size} bytes",
            metadata={"output_file": out_name, "output_path": output_file, "size": size},
        )


# ---------------------------------------------------------------------------
# video_overlay_text
# ---------------------------------------------------------------------------


class VideoOverlayText(BaseTool):
    """Burn text / subtitles onto a video (drawtext filter)."""

    @property
    def name(self) -> str:
        return "video_overlay_text"

    @property
    def description(self) -> str:
        return (
            "Burn text onto a video using ffmpeg drawtext filter. "
            "Useful for adding titles, credits, watermarks, or captions. "
            "The video is re-encoded (H.264). "
            "Supports positioning, font size, color, and time range."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Path to the input video file.",
                },
                "text": {
                    "type": "string",
                    "description": "Text to overlay (use \\n for line breaks).",
                },
                "x": {
                    "type": "string",
                    "description": "Horizontal position. Pixels or expressions like '(w-text_w)/2' for center. Default: center.",
                    "default": "(w-text_w)/2",
                },
                "y": {
                    "type": "string",
                    "description": "Vertical position. Pixels or expressions like 'h-th-20' for bottom. Default: near bottom.",
                    "default": "h-th-30",
                },
                "font_size": {
                    "type": "integer",
                    "description": "Font size in pixels. Default: 48.",
                    "default": 48,
                },
                "font_color": {
                    "type": "string",
                    "description": "Font color (ffmpeg color name or hex like 'white', 'yellow', '0xFFFFFF'). Default: white.",
                    "default": "white",
                },
                "box": {
                    "type": "boolean",
                    "description": "Draw a semi-transparent background box behind the text. Default: true.",
                    "default": True,
                },
                "start_time": {
                    "type": "number",
                    "description": "Show text from this timestamp (seconds). Default: 0.",
                    "default": 0,
                },
                "end_time": {
                    "type": "number",
                    "description": "Hide text after this timestamp (seconds). Default: entire video.",
                },
                "output_file": {
                    "type": "string",
                    "description": "Output filename (optional).",
                },
            },
            "required": ["input_file", "text"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        input_file = _sandbox_path(context, kwargs["input_file"])
        text = kwargs["text"].replace("'", "\\'").replace(":", "\\:")
        x = kwargs.get("x", "(w-text_w)/2")
        y = kwargs.get("y", "h-th-30")
        font_size = int(kwargs.get("font_size", 48))
        font_color = kwargs.get("font_color", "white")
        box = bool(kwargs.get("box", True))
        start_time = float(kwargs.get("start_time", 0))
        end_time = kwargs.get("end_time")

        if not os.path.exists(input_file):
            return ToolResult(output=f"File not found: {input_file}", is_error=True)

        ext = pathlib.Path(input_file).suffix.lstrip(".") or "mp4"
        out_name = kwargs.get("output_file") or _output_name("text", ext)
        output_file = _sandbox_path(context, out_name)

        enable_expr = f"between(t,{start_time},{end_time})" if end_time is not None else f"gte(t,{start_time})"
        box_opts = ":box=1:boxcolor=black@0.5:boxborderw=5" if box else ""
        drawtext = (
            f"drawtext=text='{text}'"
            f":x={x}:y={y}"
            f":fontsize={font_size}"
            f":fontcolor={font_color}"
            f"{box_opts}"
            f":enable='{enable_expr}'"
        )

        args = [
            "ffmpeg", "-y", "-i", input_file,
            "-vf", drawtext,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy",
            output_file,
        ]
        rc, output = await _run_ffmpeg(args, cwd=context.sandbox_path, timeout=VIDEO_TIMEOUT)
        if rc != 0:
            return ToolResult(output=f"video_overlay_text failed:\n{output}", is_error=True)

        size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        return ToolResult(
            output=f"Text overlay applied → {out_name}\nSize: {size} bytes",
            metadata={"output_file": out_name, "output_path": output_file, "size": size},
        )


# ---------------------------------------------------------------------------
# video_speed
# ---------------------------------------------------------------------------


class VideoSpeed(BaseTool):
    """Change the playback speed of a video (time-lapse or slow motion)."""

    @property
    def name(self) -> str:
        return "video_speed"

    @property
    def description(self) -> str:
        return (
            "Change the playback speed of a video. "
            "Speed > 1.0 makes it faster (time-lapse); speed < 1.0 makes it slower (slow motion). "
            "Audio pitch is preserved using atempo filter."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Path to the input video file.",
                },
                "speed": {
                    "type": "number",
                    "description": "Speed multiplier. 2.0 = 2x faster, 0.5 = half speed. Range: 0.25 – 4.0.",
                },
                "output_file": {
                    "type": "string",
                    "description": "Output filename (optional).",
                },
            },
            "required": ["input_file", "speed"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        input_file = _sandbox_path(context, kwargs["input_file"])
        speed = float(kwargs["speed"])

        if not (0.25 <= speed <= 4.0):
            return ToolResult(output="Speed must be between 0.25 and 4.0.", is_error=True)

        if not os.path.exists(input_file):
            return ToolResult(output=f"File not found: {input_file}", is_error=True)

        ext = pathlib.Path(input_file).suffix.lstrip(".") or "mp4"
        out_name = kwargs.get("output_file") or _output_name("speed", ext)
        output_file = _sandbox_path(context, out_name)

        # setpts for video speed, atempo for audio (chained for values > 2)
        vf = f"setpts={1.0 / speed:.4f}*PTS"
        # atempo accepts 0.5–2.0; chain for values outside that range
        atempo_chain = []
        s = speed
        while s > 2.0:
            atempo_chain.append("atempo=2.0")
            s /= 2.0
        while s < 0.5:
            atempo_chain.append("atempo=0.5")
            s *= 2.0
        atempo_chain.append(f"atempo={s:.4f}")
        af = ",".join(atempo_chain)

        args = [
            "ffmpeg", "-y", "-i", input_file,
            "-vf", vf,
            "-af", af,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            output_file,
        ]
        rc, output = await _run_ffmpeg(args, cwd=context.sandbox_path, timeout=VIDEO_TIMEOUT)
        if rc != 0:
            return ToolResult(output=f"video_speed failed:\n{output}", is_error=True)

        size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        return ToolResult(
            output=f"Speed {speed}x applied → {out_name}\nSize: {size} bytes",
            metadata={"output_file": out_name, "output_path": output_file, "size": size, "speed": speed},
        )
