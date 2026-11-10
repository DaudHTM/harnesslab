import json
import os
from urllib.parse import urlparse
from dataclasses import dataclass, field

import httpx


@dataclass
class Reply:
    text: str = ""
    calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class FakeProvider:
    """Deterministic integration fixture, never a benchmark performance claim."""
    def __init__(self):
        self.index = 0

    async def reply(self, messages, tools, config):
        actions = [
            ("context__get_issue", {}),
            ("repo__list_files", {}),
            ("repo__read_file", {"path": "normalizer.py"}),
            ("repo__write_file", {"path": "normalizer.py", "content": "def normalize_tags(tags):\n    return sorted({tag.strip().lower() for tag in tags if tag.strip()})\n"}),
            ("exec__run_tests", {}),
        ]
        n = self.index
        self.index += 1
        if n >= len(actions):
            return Reply(text="Implemented normalization and ran visible tests.", input_tokens=20, output_tokens=10)
        name, args = actions[n]
        return Reply(calls=[{"id": f"fake-{n}", "name": name, "arguments": args}], input_tokens=20, output_tokens=10)


class OpenAICompatibleProvider:
    async def reply(self, messages, tools, config):
        key = os.environ.get("HARNESSLAB_MODEL_API_KEY")
        if not key:
            raise RuntimeError("HARNESSLAB_MODEL_API_KEY is required")
        url = os.environ.get("HARNESSLAB_MODEL_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url + "/chat/completions", headers={"Authorization": f"Bearer {key}"},
                                         json={"model": config.model, "messages": messages, "tools": [{"type": "function", "function": t} for t in tools], "max_completion_tokens": config.max_output_tokens})
            response.raise_for_status()
        payload = response.json()
        message = payload["choices"][0]["message"]
        usage = payload["usage"]
        return Reply(message.get("content") or "", [{"id": c["id"], "name": c["function"]["name"], "arguments": json.loads(c["function"]["arguments"])} for c in message.get("tool_calls", [])], usage["prompt_tokens"], usage["completion_tokens"])


class AnthropicProvider:
    async def reply(self, messages, tools, config):
        key = os.environ.get("HARNESSLAB_ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("HARNESSLAB_ANTHROPIC_API_KEY is required")
        converted = []
        for message in messages[1:]:
            if message["role"] == "tool":
                item = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": message["tool_call_id"], "content": message["content"]}]}
            elif message["role"] == "assistant":
                content = ([{"type": "text", "text": message["content"]}] if message.get("content") else [])
                content.extend({"type": "tool_use", "id": c["id"], "name": c["function"]["name"], "input": json.loads(c["function"]["arguments"])} for c in message.get("tool_calls", []))
                item = {"role": "assistant", "content": content}
            else:
                item = {"role": message["role"], "content": [{"type": "text", "text": message["content"]}]}
            if converted and converted[-1]["role"] == item["role"]:
                converted[-1]["content"].extend(item["content"])
            else:
                converted.append(item)
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, json={"model": config.model, "system": messages[0]["content"], "messages": converted, "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools], "max_tokens": config.max_output_tokens})
            response.raise_for_status()
        payload = response.json()
        usage = payload["usage"]
        return Reply("\n".join(b["text"] for b in payload["content"] if b["type"] == "text"), [{"id": b["id"], "name": b["name"], "arguments": b["input"]} for b in payload["content"] if b["type"] == "tool_use"], usage["input_tokens"] + usage.get("cache_read_input_tokens", 0) + usage.get("cache_creation_input_tokens", 0), usage["output_tokens"])


class LocalProvider:
    """Credential-free inference restricted to loopback, never a paid remote API."""
    async def reply(self, messages, tools, config):
        url = os.environ.get("HARNESSLAB_LOCAL_MODEL_URL", "http://127.0.0.1:8080/v1").rstrip("/")
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
            raise ValueError("local provider URL must be an unauthenticated HTTP loopback endpoint")
        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            response = await client.post(url + "/chat/completions", json={"model": config.model, "messages": messages,
                "tools": [{"type": "function", "function": t} for t in tools], "max_tokens": config.max_output_tokens,
                "temperature": .2, "seed": 42, "parallel_tool_calls": False})
            response.raise_for_status()
        payload = response.json()
        message = payload["choices"][0]["message"]
        usage = payload["usage"]
        return Reply(message.get("content") or "", [{"id": c["id"], "name": c["function"]["name"],
            "arguments": json.loads(c["function"]["arguments"])} for c in message.get("tool_calls", [])],
            usage["prompt_tokens"], usage["completion_tokens"])


def provider_for(config):
    return {"fake": FakeProvider, "local": LocalProvider, "openai-compatible": OpenAICompatibleProvider, "anthropic": AnthropicProvider}[config.provider]()
