"""LLM-клиент: OpenAI → NVIDIA NIM (OpenAI-совместимые) → офлайн-fallback.

Ключи приходят из .env. Распознавание речи НЕ использует LLM — только текст
транскрипта отправляется в LLM. Если ни один ключ не задан — работают
детерминированные алгоритмы (agents/extract.py fallback), демо не ломается.
"""
from __future__ import annotations

import json
import re
import traceback

import httpx

import config

LLM_STATUS = {"provider": "none", "detail": ""}


def _extract_json(raw: str) -> dict:
    """Достаёт JSON из ответа (в т.ч. из ```json ... ```)."""
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fence:
        raw = fence.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON не найден в ответе")
    return json.loads(raw[start:end + 1])


class LLM:
    """Единая точка доступа к LLM. provider: 'openai' | 'nvidia' | None."""

    def __init__(self):
        self.provider: str | None = None
        self.api_key = ""
        self.base_url = ""
        self.model = ""
        if config.OPENAI_API_KEY:
            self.provider, self.api_key, self.base_url, self.model = (
                "openai", config.OPENAI_API_KEY, config.OPENAI_BASE_URL, config.OPENAI_MODEL)
        elif config.NVIDIA_NIM_API_KEY:
            self.provider, self.api_key, self.base_url, self.model = (
                "nvidia", config.NVIDIA_NIM_API_KEY, config.NVIDIA_NIM_BASE_URL, config.NVIDIA_NIM_MODEL)
        LLM_STATUS["provider"] = self.provider or "none"
        LLM_STATUS["detail"] = self.model if self.provider else "det algorithms (offline mode)"

    @property
    def available(self) -> bool:
        return self.provider is not None

    def chat(self, system: str, user: str, temperature: float = 0.2,
             max_tokens: int = 2000, timeout: int = 120) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload = {**body}
        try:
            with httpx.Client(timeout=timeout, trust_env=True) as client:
                r = client.post(f"{self.base_url.rstrip('/')}/chat/completions",
                                json=payload, headers=headers)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            LLM_STATUS["detail"] = f"error: {e}"
            raise

    def chat_json(self, system: str, user: str, validator=None,
                  retries: int = 2, temperature: float = 0.1) -> dict:
        """Запрос с принудительным JSON. validator(parsed) → bool."""
        last_err = None
        for attempt in range(retries + 1):
            try:
                raw = self.chat(system, user, temperature=temperature)
                parsed = _extract_json(raw)
                if validator and not validator(parsed):
                    raise ValueError("валидация JSON не пройдена")
                return parsed
            except Exception as e:
                last_err = e
        raise RuntimeError(f"LLM JSON failed: {last_err}")

    def summarize_error(self) -> str:
        return f"{self.provider or 'offline'} | {LLM_STATUS['detail']}"


_llm_singleton: LLM | None = None


def get_llm() -> LLM:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = LLM()
    return _llm_singleton


if __name__ == "__main__":
    llm = get_llm()
    print("LLM:", llm.provider, llm.model)
    print("STATUS:", LLM_STATUS)
    if llm.available:
        try:
            r = llm.chat("Ты ассистент.", "Ответь одним словом: 2+2=?")
            print("test:", r)
        except Exception as e:
            print("test failed:", e)
            traceback.print_exc()