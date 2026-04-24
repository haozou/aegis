"""Image generation tool — DALL-E via OpenAI-compatible API."""

from __future__ import annotations

import base64
import os
import pathlib
import uuid
from typing import Any

import httpx

from ..utils.logging import get_logger
from .base import BaseTool
from .types import ToolContext, ToolResult

logger = get_logger(__name__)


class ImageGenerateTool(BaseTool):
    """Generate images using DALL-E through the configured LLM proxy."""

    @property
    def name(self) -> str:
        return "image_generate"

    @property
    def description(self) -> str:
        return (
            "Generate an image from a text description using DALL-E. "
            "Returns the image saved to the sandbox. "
            "Be descriptive and specific in the prompt for best results. "
            "Supports different sizes and quality levels."
        )

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed text description of the image to generate.",
                },
                "size": {
                    "type": "string",
                    "enum": ["1024x1024", "1536x1024", "1024x1536", "auto"],
                    "description": "Image dimensions. Default: 1024x1024.",
                    "default": "1024x1024",
                },
                "quality": {
                    "type": "string",
                    "enum": ["auto", "high", "medium", "low"],
                    "description": "Image quality. 'high' is slower but more detailed. Default: auto.",
                    "default": "auto",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename (optional; auto-generated if omitted).",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        prompt = kwargs.get("prompt", "")
        if not prompt.strip():
            return ToolResult(output="Error: prompt is required", is_error=True)

        size = kwargs.get("size", "1024x1024")
        quality = kwargs.get("quality", "auto")
        filename = kwargs.get("filename") or f"generated_{uuid.uuid4().hex[:8]}.png"

        # Ensure sandbox exists
        sandbox = pathlib.Path(context.sandbox_path or "data/sandbox")
        sandbox.mkdir(parents=True, exist_ok=True)
        output_path = sandbox / filename

        # Get the LLM proxy base URL
        try:
            from ..llm.registry import get_provider
            provider = get_provider()
            base_url = getattr(provider, "_base_url", "")
            if not base_url:
                return ToolResult(
                    output="Error: No LLM proxy configured for image generation",
                    is_error=True,
                )
        except Exception as e:
            return ToolResult(output=f"Error getting provider: {e}", is_error=True)

        # Call the OpenAI-compatible images/generations endpoint
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{base_url}/v1/images/generations",
                    json={
                        "model": "gpt-image-1",
                        "prompt": prompt,
                        "n": 1,
                        "size": size,
                        "quality": quality,
                    },
                )

                if resp.status_code != 200:
                    error_text = resp.text
                    try:
                        error_data = resp.json()
                        error_text = error_data.get("error", {}).get("message", resp.text)
                    except Exception:
                        pass
                    return ToolResult(
                        output=f"Image generation failed ({resp.status_code}): {error_text}",
                        is_error=True,
                    )

                data = resp.json()
                images = data.get("data", [])
                if not images:
                    return ToolResult(output="No image returned from API", is_error=True)

                image_data = images[0]

                # Handle b64_json response
                if "b64_json" in image_data:
                    img_bytes = base64.b64decode(image_data["b64_json"])
                    output_path.write_bytes(img_bytes)
                # Handle URL response
                elif "url" in image_data:
                    img_resp = await client.get(image_data["url"])
                    img_resp.raise_for_status()
                    output_path.write_bytes(img_resp.content)
                else:
                    return ToolResult(output="Unexpected API response format", is_error=True)

            file_size = output_path.stat().st_size

            # Also save to uploads so it can be served via the file API
            upload_dir = pathlib.Path("data/uploads") / (context.user_id or "system")
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_id = uuid.uuid4().hex
            upload_path = upload_dir / f"{file_id}_{filename}"
            upload_path.write_bytes(output_path.read_bytes())

            return ToolResult(
                output=(
                    f"Image generated and saved to: {filename}\n"
                    f"Size: {file_size:,} bytes\n"
                    f"File ID: {file_id}\n"
                    f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}\n\n"
                    f"![{prompt[:60]}](/api/files/{file_id})"
                ),
                metadata={
                    "file_id": file_id,
                    "filename": filename,
                    "output_path": str(output_path),
                    "size": file_size,
                    "prompt": prompt,
                },
            )

        except httpx.TimeoutException:
            return ToolResult(output="Image generation timed out (120s)", is_error=True)
        except Exception as e:
            logger.error("Image generation failed", error=str(e))
            return ToolResult(output=f"Image generation error: {e}", is_error=True)
