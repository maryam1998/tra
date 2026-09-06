"""
Provider adapters for the multi-LLM fallback chain used by AIAgent.

Each adapter takes a ProviderConfig plus (system_prompt, user_content) and
returns the raw text reply from the model, or raises on any failure —
AIAgent catches that, logs it, and moves on to the next provider in the
priority chain.

Most of the permanent free tiers in awesome-free-llm-apis speak the
OpenAI chat-completions schema, so `call_openai_compatible` alone covers
the majority of them: Groq, OpenRouter, Mistral, NVIDIA NIM, the
Hugging Face router, OVHcloud AI Endpoints, SiliconFlow, Ollama Cloud,
Z AI (Zhipu), AionLabs, Kilo Code, LLM7.io, ModelScope, and Google
Gemini (via its `/openai/` compatibility endpoint). Anthropic and
Cohere use their own native schemas and get dedicated adapters.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict

import requests


@dataclass
class ProviderConfig:
    name: str                                  # short label, e.g. "groq" — shown in logs/rationale
    kind: str                                  # "openai" | "anthropic" | "cohere"
    base_url: str
    model: str
    api_key: str = ""
    extra_headers: Dict[str, str] = field(default_factory=dict)
    requires_key: bool = True                  # a few free tiers work anonymously (no key)

    @property
    def is_usable(self) -> bool:
        return bool(self.api_key) or not self.requires_key


def call_openai_compatible(provider: ProviderConfig, system_prompt: str, user_content: str, timeout: int) -> str:
    headers = {"content-type": "application/json", **provider.extra_headers}
    if provider.api_key:
        headers["authorization"] = f"Bearer {provider.api_key}"
    resp = requests.post(
        f"{provider.base_url.rstrip('/')}/chat/completions",
        headers=headers,
        json={
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 300,
            "temperature": 0.2,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def call_anthropic(provider: ProviderConfig, system_prompt: str, user_content: str, timeout: int) -> str:
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": provider.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": provider.model,
            "max_tokens": 300,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


def call_cohere(provider: ProviderConfig, system_prompt: str, user_content: str, timeout: int) -> str:
    resp = requests.post(
        f"{provider.base_url.rstrip('/')}/chat",
        headers={
            "authorization": f"Bearer {provider.api_key}",
            "content-type": "application/json",
        },
        json={
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data.get("message", {}).get("content", [])
    return "".join(part.get("text", "") for part in content if part.get("type") == "text")


ADAPTERS: Dict[str, Callable[[ProviderConfig, str, str, int], str]] = {
    "openai": call_openai_compatible,
    "anthropic": call_anthropic,
    "cohere": call_cohere,
}


def call_provider(provider: ProviderConfig, system_prompt: str, user_content: str, timeout: int) -> str:
    adapter = ADAPTERS.get(provider.kind)
    if adapter is None:
        raise ValueError(f"Unknown provider kind: {provider.kind!r} for provider {provider.name!r}")
    return adapter(provider, system_prompt, user_content, timeout)
