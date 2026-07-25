from __future__ import annotations

import json
import time
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import requests
from flask import current_app
from openai import OpenAI


@dataclass
class StreamResult:
    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider: str = "demo"
    model: str = "demo"
    latency_ms: int | None = None


class AIService:
    def __init__(self) -> None:
        self.provider = current_app.config["AI_PROVIDER"]

    def stream(
        self,
        history: list[dict[str, str]],
        system_prompt: str,
        model: str,
    ) -> Generator[dict[str, Any], None, StreamResult]:
        started = time.perf_counter()
        if self.provider == "openai":
            result = yield from self._stream_openai(history, system_prompt, model)
        elif self.provider == "ollama":
            result = yield from self._stream_ollama(history, system_prompt, model)
        else:
            result = yield from self._stream_demo(history, model)
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return result

    def structured_json(
        self,
        *,
        prompt: str,
        schema_name: str,
        schema: dict[str, Any],
        instructions: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Return schema-validated JSON without treating source material as instructions."""
        selected_model = model or current_app.config["OPENAI_MODEL"]
        if self.provider == "openai":
            client = OpenAI(api_key=current_app.config["OPENAI_API_KEY"])
            response = client.responses.create(
                model=selected_model,
                instructions=instructions,
                input=prompt,
                max_output_tokens=current_app.config["MAX_OUTPUT_TOKENS"],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "schema": schema,
                        "strict": True,
                    }
                },
                store=False,
            )
            return json.loads(response.output_text)
        if self.provider == "ollama":
            ollama_response = requests.post(
                f"{current_app.config['OLLAMA_BASE_URL'].rstrip('/')}/api/chat",
                json={
                    "model": selected_model or current_app.config["OLLAMA_MODEL"],
                    "messages": [
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": prompt},
                    ],
                    "format": schema,
                    "stream": False,
                },
                timeout=(10, 180),
            )
            ollama_response.raise_for_status()
            return json.loads(ollama_response.json()["message"]["content"])
        raise RuntimeError(
            "Structured AI extraction requires OpenAI or Ollama; demo mode never fabricates data"
        )

    def transcribe(self, path: Path) -> str:
        if self.provider != "openai":
            raise RuntimeError("Audio transcription requires an OpenAI provider configuration")
        client = OpenAI(api_key=current_app.config["OPENAI_API_KEY"])
        with path.open("rb") as handle:
            response = client.audio.transcriptions.create(
                model=current_app.config["TRANSCRIPTION_MODEL"],
                file=handle,
            )
        return str(response.text).strip()

    def synthesize_speech(self, text: str, output_path: Path) -> None:
        if self.provider != "openai":
            raise RuntimeError("Text-to-speech requires an OpenAI provider configuration")
        client = OpenAI(api_key=current_app.config["OPENAI_API_KEY"])
        with client.audio.speech.with_streaming_response.create(
            model=current_app.config["TTS_MODEL"],
            voice=current_app.config["TTS_VOICE"],
            input=text[:4096],
            response_format="mp3",
        ) as response:
            response.stream_to_file(output_path)

    def _stream_openai(
        self,
        history: list[dict[str, str]],
        system_prompt: str,
        model: str,
    ) -> Generator[dict[str, Any], None, StreamResult]:
        client = OpenAI(api_key=current_app.config["OPENAI_API_KEY"])
        result = StreamResult(provider="openai", model=model)
        stream = client.responses.create(
            model=model,
            instructions=system_prompt,
            input=cast(Any, history),
            max_output_tokens=current_app.config["MAX_OUTPUT_TOKENS"],
            stream=True,
            store=False,
        )
        for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                result.text += delta
                yield {"event": "delta", "data": {"text": delta}}
            elif event_type == "response.refusal.delta":
                delta = getattr(event, "delta", "")
                result.text += delta
                yield {"event": "delta", "data": {"text": delta}}
            elif event_type == "response.completed":
                response = getattr(event, "response", None)
                usage = getattr(response, "usage", None)
                if usage:
                    result.input_tokens = getattr(usage, "input_tokens", None)
                    result.output_tokens = getattr(usage, "output_tokens", None)
        return result

    def _stream_ollama(
        self,
        history: list[dict[str, str]],
        system_prompt: str,
        model: str,
    ) -> Generator[dict[str, Any], None, StreamResult]:
        ollama_model = model or current_app.config["OLLAMA_MODEL"]
        result = StreamResult(provider="ollama", model=ollama_model)
        messages = [{"role": "system", "content": system_prompt}, *history]
        with requests.post(
            f"{current_app.config['OLLAMA_BASE_URL'].rstrip('/')}/api/chat",
            json={"model": ollama_model, "messages": messages, "stream": True},
            stream=True,
            timeout=(10, 180),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                payload = json.loads(line)
                delta = payload.get("message", {}).get("content", "")
                if delta:
                    result.text += delta
                    yield {"event": "delta", "data": {"text": delta}}
                if payload.get("done"):
                    result.input_tokens = payload.get("prompt_eval_count")
                    result.output_tokens = payload.get("eval_count")
        return result

    def _stream_demo(
        self,
        history: list[dict[str, str]],
        model: str,
    ) -> Generator[dict[str, Any], None, StreamResult]:
        prompt = history[-1]["content"] if history else "Hello"
        response = (
            "Demo mode is active because no AI provider key is configured. "
            f"You asked: **{prompt}**\n\n"
            "Add `OPENAI_API_KEY` to `.env`, or set `AI_PROVIDER=ollama`, to enable a real model."
        )
        result = StreamResult(provider="demo", model=model or "demo", text="")
        for word in response.split(" "):
            delta = word + " "
            result.text += delta
            yield {"event": "delta", "data": {"text": delta}}
            time.sleep(0.015)
        result.output_tokens = max(1, len(result.text) // 4)
        return result
