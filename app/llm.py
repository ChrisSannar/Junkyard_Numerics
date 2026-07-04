"""Provider-agnostic structured LLM calls.

If OPENROUTER_API_KEY is set, calls go through OpenRouter's OpenAI-compatible
chat/completions endpoint with a JSON-schema response_format; otherwise the
Anthropic SDK (ANTHROPIC_API_KEY) is used. Either way the result is validated
against the given pydantic model, so callers are provider-blind.
"""

from __future__ import annotations

import json
import os
from typing import TypeVar

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

# .env at the repo root; real env vars win over the file
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

T = TypeVar("T", bound=BaseModel)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Anthropic model id -> OpenRouter slug
_OR_MODELS = {
    "claude-opus-4-8": "anthropic/claude-opus-4.8",
    "claude-opus-4-7": "anthropic/claude-opus-4.7",
    "claude-sonnet-5": "anthropic/claude-sonnet-5",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4.6",
    "claude-haiku-4-5": "anthropic/claude-haiku-4.5",
}


def parse_structured(schema_model: type[T], *, model: str, system: str,
                     prompt: str, max_tokens: int) -> T:
    """One structured call: system + user prompt -> validated schema_model."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return _openrouter(schema_model, model=model, system=system,
                           prompt=prompt, max_tokens=max_tokens)
    return _anthropic(schema_model, model=model, system=system,
                      prompt=prompt, max_tokens=max_tokens)


# ---------- OpenRouter path ----------

def _strict_schema(model_cls: type[BaseModel]) -> dict:
    """Pydantic schema + additionalProperties:false everywhere (strict-mode req)."""
    schema = model_cls.model_json_schema()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


def _openrouter(schema_model: type[T], *, model: str, system: str,
                prompt: str, max_tokens: int) -> T:
    slug = _OR_MODELS.get(model, model if "/" in model else f"anthropic/{model}")
    body = {
        "model": slug,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_model.__name__,
                "strict": True,
                "schema": _strict_schema(schema_model),
            },
        },
    }
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
               "Content-Type": "application/json"}
    last_err: Exception | None = None
    for attempt in range(2):
        resp = httpx.post(OPENROUTER_URL, json=body, headers=headers, timeout=600)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"OpenRouter error: {data['error']}")
        content = data["choices"][0]["message"]["content"]
        try:
            return schema_model.model_validate(json.loads(_strip_fences(content)))
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            # one retry, telling the model what was wrong with its JSON
            body["messages"].append({"role": "assistant", "content": content})
            body["messages"].append({"role": "user",
                "content": f"Your JSON failed validation: {e}. "
                           f"Respond again with ONLY corrected JSON."})
    raise RuntimeError(f"OpenRouter structured output failed validation twice: {last_err}")


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    return s.strip()


# ---------- Anthropic path ----------

_anthropic_client = None


def _anthropic(schema_model: type[T], *, model: str, system: str,
               prompt: str, max_tokens: int) -> T:
    global _anthropic_client
    import anthropic
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    messages = [{"role": "user", "content": prompt}]
    if max_tokens > 16000:
        # stream to avoid SDK HTTP-timeout guard on large outputs
        with _anthropic_client.messages.stream(
            model=model, max_tokens=max_tokens, system=system,
            messages=messages, output_format=schema_model,
        ) as stream:
            return stream.get_final_message().parsed_output
    response = _anthropic_client.messages.parse(
        model=model, max_tokens=max_tokens, system=system,
        messages=messages, output_format=schema_model,
    )
    return response.parsed_output
