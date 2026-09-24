"""
Forge LLM Registry
==================

Central model resolution for all agents and direct LLM calls.
Single place to swap providers — mirrors the pattern from bodhi/backend-new/app/llm_registry.py.

Supported providers (controlled by env vars):
  gemini   — Direct google.genai SDK calls (default, uses GOOGLE_API_KEY)
  litellm  — Capgemini internal proxy at LITELLM_ENDPOINT (yodai.capgemini.com)
             Uses OpenAI-compatible client; works with any LiteLLM proxy.

Provider selection:
  If LITELLM_ENDPOINT is set and non-empty → use litellm provider
  Otherwise → use gemini (direct Google AI Studio)

Usage
-----
ADK Agent definitions (CodeGen / Impact Analysis pipelines):
    from modules.llm_registry import get_adk_model
    agent = Agent(model=get_adk_model("design"), ...)

Direct LLM calls (RE pipeline agents — inference, gap, spec_writer):
    from modules.llm_registry import direct_llm_call
    text = await direct_llm_call(model_name="gemini-3.1-pro-preview", prompt="...")

Model names:
  The registry maps logical role names to model strings.
  When using litellm provider, LITELLM_MODEL overrides all if set.
  Otherwise per-role model names are used as-is (they're valid for the proxy too).
"""

import logging
import os
from typing import Optional

logger = logging.getLogger("forge.llm_registry")


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

def _get_provider() -> str:
    """Determine which provider to use based on env vars."""
    endpoint = os.environ.get("LITELLM_ENDPOINT", "").strip()
    if endpoint:
        return "litellm"
    return "gemini"


def _get_litellm_config() -> tuple[str, str]:
    """Return (api_key, api_base) for LiteLLM proxy."""
    api_key = os.environ.get("LITELLM_API_KEY", "")
    api_base = os.environ.get("LITELLM_ENDPOINT", "").rstrip("/")
    return api_key, api_base


def _resolve_model(model_name: str) -> str:
    """
    Resolve the model name for DIRECT LLM calls (not ADK).
    When using litellm provider, prefix model with 'gemini/' if not already prefixed.
    The yodai.capgemini.com proxy requires this prefix for Gemini models.
    """
    override = os.environ.get("LITELLM_MODEL", "").strip()
    if override:
        return override

    if _get_provider() == "litellm":
        # Proxy requires gemini/ prefix for all Gemini models in direct calls
        if not model_name.startswith("gemini/"):
            return f"gemini/{model_name}"

    return model_name


def _resolve_adk_model(model_name: str) -> str:
    """
    Resolve the model name for ADK Agent(model=...) calls.
    Returns the raw model name (no gemini/ prefix) — ADK wraps it with openai/.
    """
    override = os.environ.get("LITELLM_MODEL", "").strip()
    if override:
        return override
    return model_name


# ---------------------------------------------------------------------------
# ADK model string (for Google ADK Agent(model=...) calls)
# ---------------------------------------------------------------------------

def get_adk_model(model_name: str) -> str:
    """
    Return the model string to pass to ADK Agent(model=...).

    For provider=gemini  → returns the model name as-is (ADK handles it natively)
    For provider=litellm → prefixes with "openai/" and sets env vars so ADK
                           routes via the LiteLLM proxy.

    Args:
        model_name: Gemini model name e.g. "gemini-2.5-flash"

    Returns:
        Model string ready for ADK Agent(model=...).
    """
    provider = _get_provider()
    model = _resolve_adk_model(model_name)  # no gemini/ prefix — ADK wraps with openai/

    if provider == "litellm":
        api_key, api_base = _get_litellm_config()

        import litellm
        litellm.drop_params = True   # reasoning models reject temperature/top_p
        litellm.ssl_verify = False   # Capgemini internal CA not in Python's bundle

        os.environ["LITELLM_SSL_VERIFY"] = "False"
        if api_key:
            os.environ["LITELLM_API_KEY"] = api_key
            os.environ["OPENAI_API_KEY"] = api_key
        if api_base:
            os.environ["LITELLM_API_BASE"] = api_base
            os.environ["OPENAI_API_BASE"] = api_base

        adk_model = f"openai/{model}"
        logger.debug(f"[LLM] provider=litellm model={adk_model}")
        return adk_model

    logger.debug(f"[LLM] provider=gemini model={model}")
    return model


# ---------------------------------------------------------------------------
# Direct LLM call (for RE agents that call LLM directly, not via ADK)
# ---------------------------------------------------------------------------

async def direct_llm_call(
    model_name: str,
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.4,
    max_tokens: int = 8192,
) -> str:
    """
    Make a single-turn LLM call, routing to the correct provider.

    For provider=gemini:
        Uses google.genai client directly (sync SDK wrapped in asyncio executor).

    For provider=litellm:
        Uses openai client against the Capgemini internal proxy.
        SSL verification disabled (internal CA).

    Args:
        model_name:    Gemini model name e.g. "gemini-3.1-pro-preview"
        prompt:        User-turn prompt text.
        system_prompt: Optional system message.
        temperature:   Sampling temperature.
        max_tokens:    Maximum output tokens.

    Returns:
        String response text.
    """
    import asyncio

    provider = _get_provider()
    model = _resolve_model(model_name)

    if provider == "litellm":
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _litellm_call(model, prompt, system_prompt, temperature, max_tokens),
        )
    else:
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _gemini_call(model, prompt, system_prompt, temperature, max_tokens),
        )


def _gemini_call(
    model: str,
    prompt: str,
    system_prompt: Optional[str],
    temperature: float,
    max_tokens: int,
) -> str:
    """Direct google.genai SDK call."""
    import google.generativeai as genai

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    genai.configure(api_key=api_key)

    full_prompt = prompt
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n{prompt}"

    model_obj = genai.GenerativeModel(model)
    response = model_obj.generate_content(
        full_prompt,
        generation_config={
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        },
    )
    text = response.text or ""
    logger.debug(f"[LLM/gemini] model={model} response_chars={len(text)}")
    return text


def _litellm_call(
    model: str,
    prompt: str,
    system_prompt: Optional[str],
    temperature: float,
    max_tokens: Optional[int] = None,
    json_mode: bool = False,
) -> str:
    """OpenAI-compatible call via Capgemini LiteLLM proxy."""
    import httpx
    import openai

    api_key, api_base = _get_litellm_config()
    service_account = os.environ.get("LITELLM_SERVICE_ACCOUNT", "")

    default_headers = {}
    if service_account:
        default_headers["x-service-account"] = service_account

    http_client = httpx.Client(verify=False)
    client = openai.OpenAI(
        api_key=api_key,
        base_url=api_base,
        http_client=http_client,
        default_headers=default_headers,
    )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    logger.info(f"[LLM/litellm] → {api_base} model={model} prompt_chars={len(prompt)} json_mode={json_mode}")
    
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    
    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content or ""
    logger.debug(f"[LLM/litellm] ✓ response_chars={len(content)}")
    return content


# ---------------------------------------------------------------------------
# CodeGen llm_router compatibility shim
# (ForgeRouter._fallback_complete uses direct genai — replace with this)
# ---------------------------------------------------------------------------

async def codegen_fallback_complete(
    messages: list[dict],
    model_name: str,
    temperature: float = 0.4,
    max_tokens: int = 8192,
) -> dict:
    """
    Drop-in replacement for ForgeRouter._fallback_complete.
    Routes to litellm proxy or direct gemini based on env config.

    Returns the same dict shape as LiteLLM/OpenAI response.
    """
    import asyncio

    provider = _get_provider()
    model = _resolve_model(model_name)

    if provider == "litellm":
        response_text = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _litellm_messages_call(model, messages, temperature, max_tokens),
        )
    else:
        response_text = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _gemini_messages_call(model, messages, temperature, max_tokens),
        )

    return {
        "choices": [{"message": {"role": "assistant", "content": response_text}}],
        "model": model,
    }


def _gemini_messages_call(
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> str:
    """Gemini call from OpenAI-style messages list."""
    import google.generativeai as genai

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    genai.configure(api_key=api_key)

    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [msg["content"]]})

    model_obj = genai.GenerativeModel(model)
    response = model_obj.generate_content(
        contents,
        generation_config={
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        },
    )
    return response.text or ""


def _litellm_messages_call(
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> str:
    """LiteLLM proxy call from OpenAI-style messages list."""
    import httpx
    import openai

    api_key, api_base = _get_litellm_config()
    service_account = os.environ.get("LITELLM_SERVICE_ACCOUNT", "")

    default_headers = {}
    if service_account:
        default_headers["x-service-account"] = service_account

    http_client = httpx.Client(verify=False)
    client = openai.OpenAI(
        api_key=api_key,
        base_url=api_base,
        http_client=http_client,
        default_headers=default_headers,
    )

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""
