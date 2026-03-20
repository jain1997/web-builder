"""
Image Generator Agent.

One instance runs per image, all in parallel via LangGraph's Send API.
Supports two providers:
  - OpenAI (gpt-image-1 / DALL-E 3) — fast, high quality, uses API credits
  - Ollama (local Flux2) — free, slower, requires local GPU

Saves PNGs to disk and returns inline data URIs for Sandpack rendering.
Falls back to placehold.co on failure so the layout never breaks.
"""

import base64
from pathlib import Path

import httpx

from app.agents.state import AgentState
from app.core.config import settings
from app.core.logger import get_logger, Timer

log = get_logger(__name__)


def _placeholder_url(image_path: str) -> str:
    """Visible placeholder URL when image generation fails."""
    name = Path(image_path).stem.replace("-", " ").replace("_", " ").title()
    safe_name = name.replace(" ", "+")
    return f"https://placehold.co/600x400/1e293b/94a3b8?text={safe_name}"


def _save_image(session_id: str, image_path: str, b64_data: str) -> None:
    """Save base64 PNG to disk for persistence."""
    storage_dir = Path(settings.IMAGE_STORAGE_PATH) / session_id
    storage_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(image_path).name
    file_on_disk = storage_dir / filename
    file_on_disk.write_bytes(base64.b64decode(b64_data))


async def _generate_openai(prompt: str) -> str:
    """Generate image via OpenAI Images API. Returns base64 PNG."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.IMAGE_MODEL,
                "prompt": prompt,
                "n": 1,
                "size": settings.IMAGE_SIZE,
                "quality": settings.IMAGE_QUALITY,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["b64_json"]


async def _generate_ollama(prompt: str) -> str:
    """Generate image via local Ollama. Returns base64 PNG."""
    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={
                "model": settings.IMAGE_MODEL,
                "prompt": prompt,
                "stream": False,
            },
        )
        resp.raise_for_status()
        result = resp.json()
        image_b64 = result.get("image", "")
        if not image_b64:
            raise ValueError("Ollama returned empty image data")
        return image_b64


async def image_generator_node(state: AgentState) -> dict:
    current_image = state.get("current_image", {})
    image_path = current_image.get("path", "images/unknown.png")
    prompt = current_image.get("prompt", "")
    session_id = state.get("session_id", "default")
    provider = settings.IMAGE_PROVIDER.lower()

    log.info(f"Generating image [{provider}] -> {image_path} | \"{prompt[:80]}\"")
    t = Timer()

    try:
        if provider == "openai":
            image_b64 = await _generate_openai(prompt)
        else:
            image_b64 = await _generate_ollama(prompt)

        # Save to disk for persistence
        _save_image(session_id, image_path, image_b64)

        # Return as data URI so Sandpack can render inline
        data_uri = f"data:image/png;base64,{image_b64}"

        log.info(
            f"Done in {t.elapsed()}s -> {image_path} "
            f"({len(image_b64) // 1024}KB) [{provider}]"
        )
        return {
            "generated_image_parts": [{image_path: data_uri}],
            "current_step": [f"Generated image {image_path} ✓"],
        }

    except httpx.ConnectError:
        endpoint = "OpenAI API" if provider == "openai" else f"Ollama at {settings.OLLAMA_BASE_URL}"
        msg = f"Image {image_path}: cannot connect to {endpoint}"
        log.error(msg)
        return {
            "generated_image_parts": [{image_path: _placeholder_url(image_path)}],
            "current_step": [msg],
        }

    except httpx.TimeoutException:
        msg = f"Image {image_path}: generation timed out [{provider}]"
        log.error(msg)
        return {
            "generated_image_parts": [{image_path: _placeholder_url(image_path)}],
            "current_step": [msg],
        }

    except httpx.HTTPStatusError as e:
        body = e.response.text[:200] if e.response else ""
        msg = f"Image {image_path}: HTTP {e.response.status_code} [{provider}]"
        log.error(f"{msg} — {body}")
        return {
            "generated_image_parts": [{image_path: _placeholder_url(image_path)}],
            "current_step": [msg],
        }

    except Exception as e:
        msg = f"Image {image_path}: {type(e).__name__}: {e}"
        log.error(msg)
        return {
            "generated_image_parts": [{image_path: _placeholder_url(image_path)}],
            "current_step": [msg],
        }
