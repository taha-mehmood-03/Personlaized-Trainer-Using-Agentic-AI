"""
LangGraph-compatible Gemini LLM manager for SentiMind.

The file name is kept for backwards-compatible imports, but this module now
uses Google AI Studio / Gemini only. Third-party LLM router fallbacks are removed.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv()


DEFAULT_MODEL_GATE = "gemini-3.1-flash-lite"
DEFAULT_MODEL_MOOD = "gemini-3.1-flash-lite"
DEFAULT_MODEL_BYPASS = "gemini-3.1-flash-lite"
DEFAULT_MODEL_RESPONSE = "gemini-3.5-flash"
DEFAULT_MODEL_CRISIS = "gemini-3.1-flash-lite"
DEFAULT_MODEL_FALLBACK = "gemini-3.1-flash-lite"
DEFAULT_MODEL_ALT = "gemini-3.1-flash-lite"


def message_content_to_text(value: Any) -> str:
    """Convert LangChain/Gemini content parts into a plain text string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            text = message_content_to_text(item)
            if text:
                parts.append(text)
        return "".join(parts)
    if isinstance(value, dict):
        if "text" in value:
            return str(value.get("text") or "")
        if "content" in value:
            return message_content_to_text(value.get("content"))
        return ""
    if hasattr(value, "text"):
        return str(getattr(value, "text") or "")
    if hasattr(value, "content"):
        return message_content_to_text(getattr(value, "content"))
    return str(value)


def _is_gemini_model(value: Optional[str]) -> bool:
    return bool(value and value.strip().startswith("gemini-"))


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def _env_gemini_model(name: str, default: str) -> str:
    """
    Read a Gemini model tier from env.

    Old non-Gemini values are intentionally ignored so
    an old .env cannot silently route Google AI Studio calls to invalid models.
    """
    candidates = (
        os.getenv(f"GEMINI_{name}"),
        os.getenv(f"SENTIMIND_GEMINI_{name}"),
        os.getenv(name),
        os.getenv(f"SENTIMIND_{name}"),
    )
    for candidate in candidates:
        if not candidate:
            continue
        candidate = candidate.strip()
        if _is_gemini_model(candidate):
            return candidate
        print(f"[LLM] Ignoring non-Gemini {name}={candidate!r}; using {default}")
    return default


class GeminiLLMManager:
    """
    Backwards-compatible class name for the Gemini-only LLM manager.

    Model tiers:
      - gate/mood/background JSON: gemini-3.1-flash-lite
      - final responses:           gemini-3.5-flash
      - crisis/fallback JSON:      gemini-3.1-flash-lite
    """

    def __init__(
        self,
        api_keys: Optional[List[str]] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ):
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider = "gemini"

        self.gemini_keys = api_keys or self._load_gemini_keys()
        self.current_gemini_key_idx = 0
        self.gemini_failed_keys: set[int] = set()

        self.model_gate = _env_gemini_model("MODEL_GATE", DEFAULT_MODEL_GATE)
        self.model_mood = _env_gemini_model("MODEL_MOOD", DEFAULT_MODEL_MOOD)
        self.model_bypass = _env_gemini_model("MODEL_BYPASS", DEFAULT_MODEL_BYPASS)
        self.model_response = _env_gemini_model("MODEL_RESPONSE", DEFAULT_MODEL_RESPONSE)
        self.model_crisis = _env_gemini_model("MODEL_CRISIS", DEFAULT_MODEL_CRISIS)
        self.model_fallback = _env_gemini_model("MODEL_FALLBACK", DEFAULT_MODEL_FALLBACK)
        self.model_alt = _env_gemini_model("MODEL_ALT", DEFAULT_MODEL_ALT)
        self.model = model if _is_gemini_model(model) else self.model_response
        self.model_fast = os.getenv("GEMINI_MODEL_FAST") or os.getenv("MODEL_FAST") or self.model_mood
        if not _is_gemini_model(self.model_fast):
            self.model_fast = self.model_mood

        self._llm_cache: Dict[tuple, Any] = {}
        self._model_cooldowns: Dict[str, float] = {}

        if not self.gemini_keys:
            print("[LLM] WARNING: GEMINI_API_KEY is not set. Google AI Studio calls will fail.")

        print("[LLM] ====================================================")
        print("[LLM]   PROVIDER : Google AI Studio / Gemini only")
        print(f"[LLM]   KEYS     : {len(self.gemini_keys)} configured")
        print(f"[LLM]   GATE     : {self.model_gate}")
        print(f"[LLM]   MOOD     : {self.model_mood}")
        print(f"[LLM]   BYPASS   : {self.model_bypass}")
        print(f"[LLM]   RESPONSE : {self.model_response}")
        print(f"[LLM]   CRISIS   : {self.model_crisis}")
        print(f"[LLM]   FALLBACK : {self.model_fallback}")
        print(f"[LLM]   ALT      : {self.model_alt}")
        print("[LLM] ====================================================")

    def _load_gemini_keys(self) -> List[str]:
        keys: List[str] = []
        for i in range(1, 20):
            key = os.getenv(f"GEMINI_API_KEY_{i}")
            if not key:
                break
            if key not in keys:
                keys.append(key)

        for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            key = os.getenv(env_name)
            if key and key not in keys:
                keys.append(key)

        return keys

    def _configure_google_sdk_key_env(self, api_key: str) -> None:
        """
        The Google GenAI SDK checks env vars even when a key is passed directly.

        It prioritizes GOOGLE_API_KEY over GEMINI_API_KEY and logs a warning when
        both exist. The manager still accepts GEMINI_API_KEY for app config, but
        normalizes the process env so SDK calls use the selected rotated key.
        """
        if not api_key:
            return
        os.environ["GOOGLE_API_KEY"] = api_key
        os.environ.pop("GEMINI_API_KEY", None)

    def _get_available_gemini_key_idx(self) -> Optional[int]:
        for idx in range(len(self.gemini_keys)):
            if idx not in self.gemini_failed_keys:
                return idx
        return None

    def mark_gemini_key_failed(self) -> None:
        current_idx = self._get_available_gemini_key_idx()
        if current_idx is None:
            return

        self.gemini_failed_keys.add(current_idx)
        to_remove = [key for key in self._llm_cache if key[0] == "gemini" and key[1] == current_idx]
        for key in to_remove:
            del self._llm_cache[key]

        remaining = len(self.gemini_keys) - len(self.gemini_failed_keys)
        print(f"[LLM] Gemini key {current_idx + 1} failed. Remaining: {remaining}/{len(self.gemini_keys)}")

        if self.gemini_keys and remaining <= 0:
            print("[LLM] All Gemini keys exhausted. Resetting key rotation state.")
            self.gemini_failed_keys.clear()

    def reset_gemini_keys(self) -> None:
        self.gemini_failed_keys.clear()
        to_remove = [key for key in self._llm_cache if key[0] == "gemini"]
        for key in to_remove:
            del self._llm_cache[key]

    def _is_rate_limit_error(self, error: Exception) -> bool:
        text = str(error).lower()
        return any(marker in text for marker in ("429", "quota", "rate limit", "resource_exhausted", "too many"))

    def _is_auth_error(self, error: Exception) -> bool:
        text = str(error).lower()
        return any(marker in text for marker in ("401", "403", "api key", "permission", "unauthorized", "forbidden"))

    def _retry_after_seconds(self, error: Exception, attempt: int) -> int:
        text = str(error)
        match = re.search(r"retry[-_ ]?after['\"=: ]+(\d+)", text, flags=re.IGNORECASE)
        if match:
            try:
                return max(1, min(300, int(match.group(1))))
            except ValueError:
                pass

        try:
            default = int(os.getenv("GEMINI_MODEL_COOLDOWN_SECONDS", "45"))
        except ValueError:
            default = 45
        return max(1, min(300, default * max(1, attempt + 1)))

    def _mark_model_rate_limited(self, model: str, seconds: int) -> None:
        until = time.time() + seconds
        current = self._model_cooldowns.get(model, 0.0)
        self._model_cooldowns[model] = max(current, until)
        print(f"[LLM] Gemini model cooldown | model={model} | seconds={seconds}")

    def _model_available(self, model: str) -> bool:
        until = self._model_cooldowns.get(model)
        if not until:
            return True
        if time.time() >= until:
            del self._model_cooldowns[model]
            return True

        remaining = int(until - time.time())
        print(f"[LLM] Skipping cooled-down Gemini model | model={model} | remaining={remaining}s")
        return False

    def _model_candidates(self, preferred: Optional[str]) -> List[str]:
        return self._clean_model_candidates([preferred or self.model_response, self.model_fallback, self.model_alt])

    def _clean_model_candidates(self, models: List[Optional[str]]) -> List[str]:
        unique: List[str] = []
        seen: set[str] = set()
        for candidate in models:
            if not _is_gemini_model(candidate) or candidate in seen:
                continue
            seen.add(candidate)
            unique.append(candidate)
        return unique

    def get_model_for_task(self, task: str) -> str:
        task_key = (task or "").lower()
        if task_key in {"gate", "route", "router", "classifier", "clinical"}:
            return self.model_gate
        if task_key in {"mood", "fast", "light", "background"}:
            return self.model_mood
        if task_key in {"bypass", "casual", "chitchat"}:
            return self.model_bypass
        if task_key in {"crisis", "safety"}:
            return self.model_crisis
        if task_key in {"response", "chat", "final"}:
            return self.model_response
        return self.model

    def _bind_llm(
        self,
        llm: BaseChatModel,
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_format: Optional[dict] = None,
    ) -> BaseChatModel:
        bind_kwargs: Dict[str, Any] = {}
        if max_tokens is not None:
            bind_kwargs["max_output_tokens"] = max_tokens
        if temperature is not None:
            bind_kwargs["temperature"] = temperature
        if response_format is not None:
            bind_kwargs["response_mime_type"] = "application/json"
        bind_kwargs["automatic_function_calling"] = {"disable": True}
        return llm.bind(**bind_kwargs) if bind_kwargs else llm

    def _get_gemini_llm(self, model: Optional[str] = None) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not self.gemini_keys:
            raise ValueError("[LLM] GEMINI_API_KEY not configured. Set GEMINI_API_KEY in .env")

        key_idx = self._get_available_gemini_key_idx()
        if key_idx is None:
            self.reset_gemini_keys()
            key_idx = self._get_available_gemini_key_idx()
        if key_idx is None:
            raise RuntimeError("[LLM] No available Gemini API keys.")

        effective_model = model if _is_gemini_model(model) else self.model
        cache_key = ("gemini", key_idx, effective_model)

        if cache_key not in self._llm_cache:
            print(f"[LLM] NEW Gemini instance | key={key_idx + 1}/{len(self.gemini_keys)} | model={effective_model}")
            self._configure_google_sdk_key_env(self.gemini_keys[key_idx])
            self._llm_cache[cache_key] = ChatGoogleGenerativeAI(
                model=effective_model,
                api_key=self.gemini_keys[key_idx],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                streaming=True,
            )
        return self._llm_cache[cache_key]

    def get_llm(self, model: Optional[str] = None, reasoning: Optional[dict] = None) -> BaseChatModel:
        return self._get_gemini_llm(model=model)

    def get_gemini_llm(self, model: Optional[str] = None) -> BaseChatModel:
        return self._get_gemini_llm(model=model)

    async def ainvoke_gemini_with_rotation(
        self,
        messages,
        *,
        model: Optional[str] = None,
        model_candidates: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_format: Optional[dict] = None,
        response_format_models: Optional[List[str]] = None,
        config: Optional[dict] = None,
    ):
        candidates = self._clean_model_candidates(model_candidates or self._model_candidates(model))
        attempts = max(1, len(self.gemini_keys))
        last_error: Optional[Exception] = None

        for candidate in candidates:
            if not self._model_available(candidate):
                continue

            for attempt in range(attempts):
                try:
                    llm = self._get_gemini_llm(model=candidate)
                    llm = self._bind_llm(
                        llm,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        response_format=response_format,
                    )
                    return await llm.ainvoke(messages, config=config)
                except Exception as exc:
                    last_error = exc
                    key_idx = self._get_available_gemini_key_idx()
                    key_label = (key_idx + 1) if key_idx is not None else "none"
                    print(
                        f"[LLM] Gemini call failed | model={candidate} | "
                        f"key={key_label}/{len(self.gemini_keys)} | error={str(exc)[:120]}"
                    )

                    if self._is_rate_limit_error(exc):
                        retry_after = self._retry_after_seconds(exc, attempt)
                        self._mark_model_rate_limited(candidate, retry_after)
                        break

                    # Do not raise here; continue trying other keys and models.
                    pass

        if last_error:
            if self._is_rate_limit_error(last_error) or "Too Many Requests" in str(last_error) or "429" in str(last_error):
                from langchain_core.messages import AIMessage as _AI
                msg = (
                    "I'm experiencing a brief technical pause — my response systems are "
                    "temporarily at capacity. Give me a moment and try again. I'm still here for you. 💙"
                )
                print(f"[LLM] DEGRADED: All models rate-limited (ainvoke) — returning graceful fallback")
                return _AI(content=msg)
            raise last_error
        raise RuntimeError("[LLM] Gemini call failed: no available model/key candidates")

    def invoke_gemini_with_rotation(
        self,
        messages,
        *,
        model: Optional[str] = None,
        model_candidates: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_format: Optional[dict] = None,
        response_format_models: Optional[List[str]] = None,
    ):
        candidates = self._clean_model_candidates(model_candidates or self._model_candidates(model))
        attempts = max(1, len(self.gemini_keys))
        last_error: Optional[Exception] = None

        for candidate in candidates:
            if not self._model_available(candidate):
                continue

            for attempt in range(attempts):
                try:
                    llm = self._get_gemini_llm(model=candidate)
                    llm = self._bind_llm(
                        llm,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        response_format=response_format,
                    )
                    return llm.invoke(messages)
                except Exception as exc:
                    last_error = exc
                    key_idx = self._get_available_gemini_key_idx()
                    key_label = (key_idx + 1) if key_idx is not None else "none"
                    print(
                        f"[LLM] Gemini sync call failed | model={candidate} | "
                        f"key={key_label}/{len(self.gemini_keys)} | error={str(exc)[:120]}"
                    )

                    if self._is_rate_limit_error(exc):
                        retry_after = self._retry_after_seconds(exc, attempt)
                        self._mark_model_rate_limited(candidate, retry_after)
                        break

                    if self._is_auth_error(exc):
                        self.mark_gemini_key_failed()
                        continue

                    # Do not raise here; continue trying other keys and models.
                    pass

        if last_error:
            if self._is_rate_limit_error(last_error) or "Too Many Requests" in str(last_error) or "429" in str(last_error):
                from langchain_core.messages import AIMessage as _AI
                msg = (
                    "I'm experiencing a brief technical pause — my response systems are "
                    "temporarily at capacity. Give me a moment and try again. I'm still here for you. 💙"
                )
                print(f"[LLM] DEGRADED: All models rate-limited (invoke) — returning graceful fallback")
                return _AI(content=msg)
            raise last_error
        raise RuntimeError("[LLM] Gemini call failed: no available model/key candidates")

    async def astream_gemini_with_rotation(
        self,
        messages,
        *,
        model: Optional[str] = None,
        model_candidates: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_format: Optional[dict] = None,
        response_format_models: Optional[List[str]] = None,
        config: Optional[dict] = None,
    ) -> AsyncIterator[Any]:
        candidates = self._clean_model_candidates(model_candidates or self._model_candidates(model))
        attempts = max(1, len(self.gemini_keys))
        last_error: Optional[Exception] = None

        for candidate in candidates:
            if not self._model_available(candidate):
                continue

            for attempt in range(attempts):
                emitted_token = False
                try:
                    llm = self._get_gemini_llm(model=candidate)
                    llm = self._bind_llm(
                        llm,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        response_format=response_format,
                    )
                    async for chunk in llm.astream(messages, config=config):
                        emitted_token = True
                        yield chunk
                    return
                except Exception as exc:
                    last_error = exc
                    if emitted_token:
                        raise

                    key_idx = self._get_available_gemini_key_idx()
                    key_label = (key_idx + 1) if key_idx is not None else "none"
                    print(
                        f"[LLM] Gemini stream failed | model={candidate} | "
                        f"key={key_label}/{len(self.gemini_keys)} | error={str(exc)[:120]}"
                    )

                    if self._is_rate_limit_error(exc):
                        retry_after = self._retry_after_seconds(exc, attempt)
                        self._mark_model_rate_limited(candidate, retry_after)
                        break

                    if self._is_auth_error(exc):
                        self.mark_gemini_key_failed()
                        continue

                    # Do not raise here; continue trying other keys and models.
                    pass

        if last_error:
            if self._is_rate_limit_error(last_error) or "Too Many Requests" in str(last_error) or "429" in str(last_error):
                from langchain_core.messages import AIMessageChunk as _AIChunk
                msg = (
                    "I'm experiencing a brief technical pause — my response systems are "
                    "temporarily at capacity. Give me a moment and try again. I'm still here for you. 💙"
                )
                print(f"[LLM] DEGRADED: All models rate-limited (astream) — yielding graceful fallback chunk")
                yield _AIChunk(content=msg)
                return
            raise last_error

        # All candidates were in cooldown — reset cooldowns and retry once with the first candidate.
        if candidates:
            print("[LLM] All candidates in cooldown; resetting cooldowns and retrying once.")
            for c in candidates:
                self._model_cooldowns.pop(c, None)
            candidate = candidates[0]
            try:
                llm = self._get_gemini_llm(model=candidate)
                llm = self._bind_llm(llm, max_tokens=max_tokens, temperature=temperature, response_format=response_format)
                async for chunk in llm.astream(messages, config=config):
                    yield chunk
                return
            except Exception as exc:
                from langchain_core.messages import AIMessageChunk as _AIChunk
                msg = (
                    "I'm experiencing a brief technical pause — my response systems are "
                    "temporarily at capacity. Give me a moment and try again. I'm still here for you. 💙"
                )
                print(f"[LLM] DEGRADED: Cooldown-reset retry also failed ({str(exc)[:80]}) — yielding graceful fallback")
                yield _AIChunk(content=msg)
                return

        raise RuntimeError("[LLM] Gemini stream failed: no available model/key candidates")

    def get_status(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "gemini_keys_total": len(self.gemini_keys),
            "gemini_keys_active": len(self.gemini_keys) - len(self.gemini_failed_keys),
            "model": self.model,
            "model_gate": self.model_gate,
            "model_mood": self.model_mood,
            "model_bypass": self.model_bypass,
            "model_response": self.model_response,
            "model_crisis": self.model_crisis,
            "model_fallback": self.model_fallback,
            "model_alt": self.model_alt,
            "model_cooldowns": {
                model: max(0, int(until - time.time()))
                for model, until in self._model_cooldowns.items()
                if until > time.time()
            },
            "gemini_key_set": bool(self.gemini_keys),
        }


MultiKeyGroqChat = GeminiLLMManager

_llm_manager: Optional[GeminiLLMManager] = None


def get_llm_manager() -> GeminiLLMManager:
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = GeminiLLMManager()
    return _llm_manager


async def invoke_llm(
    messages,
    model: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    manager = get_llm_manager()
    response = await manager.ainvoke_gemini_with_rotation(
        messages,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return message_content_to_text(response.content)


def get_chat_llm() -> BaseChatModel:
    manager = get_llm_manager()
    return manager.get_llm(model=getattr(manager, "model_response", None))


def get_llm_with_tools(tools: list) -> BaseChatModel:
    llm = get_chat_llm()
    return llm.bind_tools(tools)
