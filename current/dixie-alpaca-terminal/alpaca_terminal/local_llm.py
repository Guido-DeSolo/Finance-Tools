"""Fixed-model client for the local Ollama chat API."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Change this one value when Dixie should use a different specific local model.
# There is deliberately no model picker or per-request model override in the UI.
LOCAL_LLM_MODEL = "analyst:latest"
LOCAL_LLM_URL = "http://127.0.0.1:11434/api/chat"
SYSTEM_PROMPT = (
    "You are the local assistant embedded in Dixie Finance Terminal. Be concise, "
    "distinguish facts from uncertainty, and never claim that informational market "
    "analysis is personalized financial advice."
)


class LocalLLMError(RuntimeError):
    pass


class LocalLLM:
    def __init__(self, timeout: float = 180):
        self.timeout = timeout

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": LOCAL_LLM_MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            "stream": False,
        }
        request = Request(
            LOCAL_LLM_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "dixie-finance-terminal/1"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                envelope: Any = json.load(response)
        except HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:500]
            error.close()
            raise LocalLLMError(f"Ollama HTTP {error.code}: {detail}") from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise LocalLLMError(f"Local LLM request failed: {error}") from error
        message = envelope.get("message") if isinstance(envelope, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LocalLLMError("Local LLM returned no message content")
        return content.strip()
