"""
Image Generator Agent.

One instance runs per image, all in parallel via LangGraph's Send API.
Calls local Ollama text-to-image model, saves PNG to disk, and returns
a URL path so generated code can reference it via <img src="...">.

Reports errors visibly in agent steps so the user can see what failed.
"""

import base64
from pathlib import Path

import httpx

from app.agents.state import AgentState
from app.core.config import settings
from app.core.logger import get_logger, Timer

log = get_logger(__name__)

# 1x1 transparent PNG — used when image generation fails so code doesn't break.
_PLACEHOLDER_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQAB"
    "Nl7BcQAAAABJRU5ErkJggg=="
)
_PLACEHOLDER_URI = f"data:image/png;base64,{_PLACEHOLDER_B64}"


def _save_image(session_id: str, image_path: str, b64_data: str) -> str:
    """Save base64 PNG to disk and return the public URL."""
    storage_dir = Path(settings.IMAGE_STORAGE_PATH) / session_id
    storage_dir.mkdir(parents=True, exist_ok=True)

    # image_path is like "images/hero.png" — extract filename
    filename = Path(image_path).name
    file_on_disk = storage_dir / filename
    file_on_disk.write_bytes(base64.b64decode(b64_data))

    # Return URL the frontend can fetch
    return f"{settings.PUBLIC_URL}/api/images/{session_id}/{filename}"


async def image_generator_node(state: AgentState) -> dict:
    current_image = state.get("current_image", {})
    image_path = current_image.get("path", "images/unknown.png")
    prompt = current_image.get("prompt", "")
    session_id = state.get("session_id", "default")

    log.info(f"Generating image -> {image_path} | \"{prompt[:80]}\"")
    t = Timer()

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_IMAGE_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            result = resp.json()

        image_b64 = result.get("image", "")
        if not image_b64:
            log.warning(f"Ollama returned empty image for {image_path}")
            return {
                "generated_image_parts": [{image_path: _PLACEHOLDER_URI}],
                "current_step": [f"Image {image_path}: Ollama returned empty response (using placeholder)"],
            }

        # Save to disk and get URL
        url = _save_image(session_id, image_path, image_b64)

        log.info(
            f"Done in {t.elapsed()}s -> {image_path} "
            f"({len(image_b64) // 1024}KB) saved to disk"
        )
        return {
            "generated_image_parts": [{image_path: url}],
            "current_step": [f"Generated image {image_path} ✓"],
        }

    except httpx.ConnectError:
        msg = f"Image {image_path}: Ollama not reachable at {settings.OLLAMA_BASE_URL} (is it running?)"
        log.error(msg)
        return {
            "generated_image_parts": [{image_path: _PLACEHOLDER_URI}],
            "current_step": [msg],
        }

    except httpx.TimeoutException:
        msg = f"Image {image_path}: generation timed out (180s)"
        log.error(msg)
        return {
            "generated_image_parts": [{image_path: _PLACEHOLDER_URI}],
            "current_step": [msg],
        }

    except httpx.HTTPStatusError as e:
        msg = f"Image {image_path}: Ollama HTTP {e.response.status_code}"
        log.error(f"{msg} — {e.response.text[:200]}")
        return {
            "generated_image_parts": [{image_path: _PLACEHOLDER_URI}],
            "current_step": [msg],
        }

    except Exception as e:
        msg = f"Image {image_path}: unexpected error — {type(e).__name__}: {e}"
        log.error(msg)
        return {
            "generated_image_parts": [{image_path: _PLACEHOLDER_URI}],
            "current_step": [msg],
        }
