"""
Benchmark Gemini models for SentiMind routing workloads.

Usage:
  python scripts/benchmark_gemini_models.py

Requires:
  GEMINI_API_KEY or GEMINI_API_KEY_1 in the environment/.env file.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types


DEFAULT_MODELS = [
    "gemini-3.1-flash-lite",
]

PROMPTS = [
    "I feel really anxious about my viva next month.",
    "Since before Eid, maybe a month now.",
    "Can you suggest something practical before I study tonight?",
    "I do not think that exercise suits me; my mind argued with it.",
    "What was the first technique you suggested?",
]

SYSTEM_PROMPT = """You are a fast JSON router for a mental-health wellness app.
Classify the user message into exactly one route:
chitchat, therapeutic, contextual_followup, technique_request,
technique_follow_up, memory_query, positive_feedback, crisis.

Return ONLY valid JSON:
{"route":"therapeutic","confidence":0.0,"reasoning":"short phrase"}"""


@dataclass
class Result:
    model: str
    prompt: str
    ok: bool
    first_token_ms: float | None
    total_ms: float
    json_ok: bool
    route: str | None
    error: str | None = None


def _api_key() -> str:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_1") or os.getenv("GOOGLE_API_KEY") or ""


def _parse_json(text: str) -> tuple[bool, str | None]:
    clean = text.strip()
    if "```" in clean:
        clean = clean.replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(clean)
        route = parsed.get("route") if isinstance(parsed, dict) else None
        return isinstance(route, str), route
    except Exception:
        return False, None


def _stream_call(client: genai.Client, model: str, prompt: str, json_mode: bool) -> Result:
    started = time.perf_counter()
    first_token_ms: float | None = None
    content_parts: list[str] = []

    config: dict[str, Any] = {
        "system_instruction": SYSTEM_PROMPT,
        "temperature": 0,
        "max_output_tokens": 120,
    }
    if json_mode:
        config["response_mime_type"] = "application/json"

    try:
        stream = client.models.generate_content_stream(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config),
        )
        for chunk in stream:
            token = getattr(chunk, "text", None) or ""
            if token:
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - started) * 1000
                content_parts.append(token)

        total_ms = (time.perf_counter() - started) * 1000
        json_ok, route = _parse_json("".join(content_parts))
        return Result(model, prompt, True, first_token_ms, total_ms, json_ok, route)
    except Exception as exc:
        return Result(
            model=model,
            prompt=prompt,
            ok=False,
            first_token_ms=None,
            total_ms=(time.perf_counter() - started) * 1000,
            json_ok=False,
            route=None,
            error=str(exc)[:300],
        )


def _summarize(results: list[Result]) -> list[dict[str, Any]]:
    rows = []
    for model in sorted({result.model for result in results}):
        model_results = [result for result in results if result.model == model]
        ok_results = [result for result in model_results if result.ok]
        first_tokens = [result.first_token_ms for result in ok_results if result.first_token_ms is not None]
        totals = [result.total_ms for result in ok_results]
        rows.append({
            "model": model,
            "calls": len(model_results),
            "ok": sum(1 for result in model_results if result.ok),
            "json_ok": sum(1 for result in model_results if result.json_ok),
            "json_rate": round(sum(1 for result in model_results if result.json_ok) / max(1, len(model_results)), 2),
            "first_token_p50_ms": round(statistics.median(first_tokens), 1) if first_tokens else None,
            "total_p50_ms": round(statistics.median(totals), 1) if totals else None,
            "errors": [result.error for result in model_results if result.error][:2],
        })
    return rows


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    parser.add_argument("--no-json-mode", action="store_true", help="Do not request Gemini JSON mode.")
    parser.add_argument("--json", action="store_true", help="Print raw JSON results.")
    args = parser.parse_args()

    api_key = _api_key()
    if not api_key:
        print("Missing GEMINI_API_KEY, GEMINI_API_KEY_1, or GOOGLE_API_KEY.")
        return 2

    client = genai.Client(api_key=api_key)
    results: list[Result] = []
    for model in args.models:
        for prompt in PROMPTS:
            result = _stream_call(client, model, prompt, json_mode=not args.no_json_mode)
            results.append(result)
            status = "JSON" if result.json_ok else "FAIL"
            print(
                f"{status:4} | {model:28} | "
                f"first={result.first_token_ms or 0:7.1f}ms | "
                f"total={result.total_ms:7.1f}ms | {prompt[:44]}"
            )

    summary = _summarize(results)
    print("\nSummary")
    print(json.dumps(summary, indent=2))
    if args.json:
        print("\nRaw")
        print(json.dumps([result.__dict__ for result in results], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
