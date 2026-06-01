"""Async Ollama API client with JSON mode and retry logic."""
import json
import logging
# pyrefly: ignore [missing-import]
import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_SUMMARY_MODEL

log = logging.getLogger(__name__)

# ── Default LLM options ──────────────────────────────────────────────
DEFAULT_OPTIONS = {
    "temperature": 0.3,
    "num_predict": 4096,
}


async def generate(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    timeout: float = 300.0,
    seed: int = 42,
) -> dict:
    """Call Ollama /api/generate and return parsed JSON.

    Args:
        prompt:      User prompt text.
        system:      Optional system prompt.
        model:       Override model (defaults to config OLLAMA_MODEL).
        temperature: Sampling temperature (0 = fully deterministic).
        max_tokens:  Max tokens to generate.
        timeout:     HTTP timeout in seconds.
        seed:        Random seed for reproducibility.

    Returns:
        Parsed JSON dict from the LLM response.

    Raises:
        ValueError: If the LLM response is not valid JSON.
        httpx.HTTPError: On network / Ollama errors.
    """
    model = model or OLLAMA_MODEL
    url = f"{OLLAMA_BASE_URL}/api/generate"

    payload = {
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "seed": seed,
        },
    }
    if system:
        payload["system"] = system

    log.info(f"LLM call → model={model}, prompt_len={len(prompt)}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()

    data = resp.json()
    raw_text = data.get("response", "")

    log.debug(f"LLM raw response (first 500 chars): {raw_text[:500]}")

    # Parse JSON from LLM output (strip markdown fences if present)
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        # Remove ```json ... ``` or ``` ... ```
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fallback: find first { ... } block in the response
    import re
    json_match = re.search(r'\{[\s\S]*\}', cleaned)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    log.error(f"LLM returned invalid JSON.\nRaw (first 1000 chars): {raw_text[:1000]}")
    raise ValueError(f"LLM did not return valid JSON. Response starts with: {raw_text[:200]}")


async def generate_text(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    timeout: float = 120.0,
) -> str:
    """Call Ollama /api/generate and return plain text (no JSON parsing).

    Used for clinical summary generation where the output is narrative prose.

    Args:
        prompt:      User prompt text.
        system:      Optional system prompt.
        model:       Override model (defaults to OLLAMA_SUMMARY_MODEL).
        temperature: Sampling temperature.
        max_tokens:  Max tokens to generate.
        timeout:     HTTP timeout in seconds.

    Returns:
        Plain text string from the LLM response.
    """
    model = model or OLLAMA_SUMMARY_MODEL
    url = f"{OLLAMA_BASE_URL}/api/generate"

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if system:
        payload["system"] = system

    log.info(f"LLM text call → model={model}, prompt_len={len(prompt)}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()

    data = resp.json()
    text = data.get("response", "").strip()
    log.debug(f"LLM text response (first 300 chars): {text[:300]}")
    return text


async def check_health() -> dict:
    """Check if Ollama is running and return model info."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            tags = resp.json()
            models = [m["name"] for m in tags.get("models", [])]
            return {
                "ollama": "connected",
                "configured_model": OLLAMA_MODEL,
                "available_models": models,
                "model_loaded": OLLAMA_MODEL in models
                or any(OLLAMA_MODEL in m for m in models),
            }
    except Exception as e:
        return {"ollama": "disconnected", "error": str(e)}
