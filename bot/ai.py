from __future__ import annotations

import asyncio
import json
from collections import defaultdict

import aiohttp

from .config import Settings


class OllamaClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._history: dict[str, list[dict[str, str]]] = defaultdict(list)

    async def ask(self, chat_id: str, question: str) -> str:
        messages = [
            {"role": "system", "content": self.settings.system_prompt},
            *self._history[chat_id],
            {"role": "user", "content": question},
        ]
        options = {
            "temperature": 0.7,
            "num_predict": self.settings.ollama_num_predict,
        }
        if self.settings.ollama_num_thread:
            options["num_thread"] = self.settings.ollama_num_thread
        if self.settings.ollama_num_gpu is not None:
            options["num_gpu"] = self.settings.ollama_num_gpu

        payload = {
            "model": self.settings.ollama_model,
            "stream": False,
            "keep_alive": self.settings.ollama_keep_alive,
            "messages": messages,
            "options": options,
        }
        timeout = aiohttp.ClientTimeout(total=self.settings.ollama_timeout_seconds)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.settings.ollama_url}/api/chat", json=payload
                ) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise RuntimeError(f"Ollama returned HTTP {response.status}: {body}")
                    data = json.loads(body)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("Ollama took too long to answer.") from exc
        except aiohttp.ClientError as exc:
            raise RuntimeError("Could not reach Ollama. Is `ollama serve` running?") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama returned invalid JSON.") from exc

        answer = (data.get("message") or {}).get("content", "").strip()
        if not answer:
            raise RuntimeError("Ollama returned an empty answer.")

        self._remember(chat_id, "user", question)
        self._remember(chat_id, "assistant", answer)
        return answer

    def reset(self, chat_id: str) -> None:
        self._history.pop(chat_id, None)

    def _remember(self, chat_id: str, role: str, content: str) -> None:
        history = self._history[chat_id]
        history.append({"role": role, "content": content})
        del history[:-8]
