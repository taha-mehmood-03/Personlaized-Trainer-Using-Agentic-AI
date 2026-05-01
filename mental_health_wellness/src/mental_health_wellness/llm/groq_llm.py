"""
LangGraph-Compatible LLM Wrapper
OpenRouter (FIRST PRIORITY) with Groq fallback.
- OpenRouter: uses langchain_openai.ChatOpenAI with https://openrouter.ai/api/v1
- Groq fallback: used only when LLM_PROVIDER != 'openrouter' or OpenRouter fails

MODEL SELECTION (v6.1 — Best for Mental Health AI):
  Heavy tasks (crisis detection, empathetic response generation):
    → anthropic/claude-3.5-sonnet  — best empathy, nuanced reasoning, safety
  Fast tasks (emotion classification, intent, distortion detection):
    → anthropic/claude-3-haiku  — ultra-fast, cost-efficient JSON classification
"""

import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv()

# ============================================
# MODEL NAME MAPPING
# Translates legacy Groq/LLaMA model names → best OpenRouter equivalents
# for a mental health use case (empathy, safety, structured classification).
# ============================================
GROQ_TO_OPENROUTER_MODEL_MAP = {
    # Heavy / reasoning tasks → Claude 3.5 Sonnet (best empathy + safety)
    "llama-3.3-70b-versatile":  "anthropic/claude-3.5-sonnet",
    "llama-3.1-70b-versatile":  "anthropic/claude-3.5-sonnet",
    "llama3-70b-8192":          "anthropic/claude-3.5-sonnet",
    "llama-3.1-8b-instant":     "anthropic/claude-3-haiku",
    "llama3-8b-8192":           "anthropic/claude-3-haiku",
    "mixtral-8x7b-32768":       "anthropic/claude-3-haiku",
    # Google models pass through unchanged
    "gemma-7b-it":              "google/gemma-7b-it",
    # Legacy Claude names → current best versions
    "anthropic/claude-3-opus":  "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3-haiku": "anthropic/claude-3-haiku",
}


def _resolve_openrouter_model(model: str) -> str:
    """Map a Groq model name to its OpenRouter equivalent, or pass through if already OpenRouter-style."""
    return GROQ_TO_OPENROUTER_MODEL_MAP.get(model, model)


class MultiKeyGroqChat:
    """
    Unified LLM Manager.

    Priority 1 — OpenRouter (when LLM_PROVIDER=openrouter):
      Uses langchain_openai.ChatOpenAI pointed at https://openrouter.ai/api/v1.
      Single API key, no rotation needed (OpenRouter handles load internally).

    Priority 2 — Groq (fallback, when LLM_PROVIDER=groq or OpenRouter unavailable):
      Multi-key pool with automatic rotation on rate limits.
    """

    def __init__(
        self,
        api_keys: Optional[List[str]] = None,
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ):
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.provider = os.getenv("LLM_PROVIDER", "openrouter").lower()

        # ── OpenRouter setup ──────────────────────────────────────
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        # Default model fallbacks — overridden by .env MODEL / MODEL_FAST
        self.model = model or os.getenv("MODEL", "anthropic/claude-3.5-sonnet")
        self.model_fast = os.getenv("MODEL_FAST", "anthropic/claude-3-haiku")

        # ── Groq fallback setup ───────────────────────────────────
        self.groq_api_keys = api_keys or self._load_groq_keys()
        self.current_groq_key_idx = 0
        self.groq_failed_keys: set = set()

        # Instance cache keyed by (provider, key_idx_or_0, model)
        self._llm_cache: Dict[tuple, Any] = {}

        if self.provider == "openrouter":
            if not self.openrouter_api_key:
                raise ValueError(
                    "LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is not set in .env"
                )
            print("[LLM] ╔══════════════════════════════════════════════════════════╗")
            print(f"[LLM] ║  PROVIDER : OpenRouter                                  ║")
            print(f"[LLM] ║  HEAVY    : {self.model:<46}║")
            print(f"[LLM] ║  FAST     : {self.model_fast:<46}║")
            print("[LLM] ╚══════════════════════════════════════════════════════════╝")
        else:
            if not self.groq_api_keys:
                raise ValueError(
                    "No Groq API keys found. Set GROQ_API_KEY or GROQ_API_KEY_1, GROQ_API_KEY_2, etc. in .env"
                )
            print(f"[LLM] ⚠️  PROVIDER: Groq (fallback) | {len(self.groq_api_keys)} key(s) loaded")

    # ------------------------------------------------------------------
    # Key loaders
    # ------------------------------------------------------------------

    def _load_groq_keys(self) -> List[str]:
        """Load numbered GROQ_API_KEY_1 … or fall back to GROQ_API_KEY."""
        keys = []
        i = 1
        while True:
            key = os.getenv(f"GROQ_API_KEY_{i}")
            if not key:
                break
            keys.append(key)
            i += 1
        if not keys:
            key = os.getenv("GROQ_API_KEY")
            if key:
                keys.append(key)
        return keys

    def _load_openai_keys(self) -> List[str]:
        keys = []
        i = 1
        while True:
            key = os.getenv(f"OPENAI_API_KEY_{i}")
            if not key:
                break
            keys.append(key)
            i += 1
        if not keys:
            key = os.getenv("OPENAI_API_KEY")
            if key:
                keys.append(key)
        return keys

    # ------------------------------------------------------------------
    # Groq helpers
    # ------------------------------------------------------------------

    def _get_available_groq_key_idx(self) -> Optional[int]:
        """Get next valid Groq key index, or None if all failed."""
        for idx in range(len(self.groq_api_keys)):
            if idx not in self.groq_failed_keys:
                return idx
        return None

    def mark_key_failed(self):
        """Mark current Groq key as failed and rotate to next one."""
        current_idx = self._get_available_groq_key_idx()
        if current_idx is not None:
            self.groq_failed_keys.add(current_idx)
            to_remove = [k for k in self._llm_cache if k[1] == current_idx]
            for k in to_remove:
                del self._llm_cache[k]
            remaining = len(self.groq_api_keys) - len(self.groq_failed_keys)
            print(f"[LLM] ⚠️ Groq Key {current_idx + 1} marked failed. Remaining: {remaining}/{len(self.groq_api_keys)}")

    # ------------------------------------------------------------------
    # Core: get_llm()
    # ------------------------------------------------------------------

    def get_llm(self, model: Optional[str] = None) -> BaseChatModel:
        """
        Return a ready-to-use LLM instance.

        - OpenRouter path: uses ChatOpenAI with openrouter base_url.
          Model names are auto-mapped from Groq names to OpenRouter names.
        - Groq path: multi-key rotation (legacy fallback).
        """
        if self.provider == "openrouter":
            return self._get_openrouter_llm(model)
        else:
            return self._get_groq_llm(model)

    def _get_openrouter_llm(self, model: Optional[str] = None) -> BaseChatModel:
        """Build/cache a ChatOpenAI instance pointed at OpenRouter."""
        from langchain_openai import ChatOpenAI

        # Resolve model name (handles Groq → OpenRouter mapping transparently)
        raw_model = model or self.model
        effective_model = _resolve_openrouter_model(raw_model)

        cache_key = ("openrouter", 0, effective_model)

        if cache_key not in self._llm_cache:
            print(f"[LLM] 🌐 NEW OpenRouter instance | model={effective_model}")
            self._llm_cache[cache_key] = ChatOpenAI(
                api_key=self.openrouter_api_key,
                base_url=self.openrouter_base_url,
                model=effective_model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                streaming=True,
                default_headers={
                    "HTTP-Referer": "https://sentimind.app",
                    "X-Title": "SentiMind Mental Health AI",
                },
            )
        else:
            print(f"[LLM] ⚡ Cached OpenRouter instance | model={effective_model}")

        return self._llm_cache[cache_key]

    def _get_groq_llm(self, model: Optional[str] = None) -> BaseChatModel:
        """Build/cache a ChatGroq instance with key rotation (fallback path)."""
        from langchain_groq import ChatGroq

        key_idx = self._get_available_groq_key_idx()

        if key_idx is None:
            print(f"[LLM] ⚠️ All Groq keys exhausted. Resetting...")
            self.groq_failed_keys.clear()
            self._llm_cache.clear()
            key_idx = self._get_available_groq_key_idx()

        if key_idx is None:
            raise RuntimeError("No valid Groq API keys available")

        effective_model = model or self.model
        cache_key = ("groq", key_idx, effective_model)

        if cache_key not in self._llm_cache:
            print(f"[LLM] 🔑 NEW Groq instance | key={key_idx + 1}/{len(self.groq_api_keys)} | model={effective_model}")
            self._llm_cache[cache_key] = ChatGroq(
                api_key=self.groq_api_keys[key_idx],
                model=effective_model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                streaming=True,
            )
        else:
            print(f"[LLM] ⚡ Cached Groq instance | key={key_idx + 1}/{len(self.groq_api_keys)} | model={effective_model}")

        return self._llm_cache[cache_key]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Get current status."""
        if self.provider == "openrouter":
            return {
                "provider": "openrouter",
                "model": self.model,
                "model_fast": self.model_fast,
                "openrouter_key_set": bool(self.openrouter_api_key),
            }
        return {
            "provider": "groq",
            "groq_keys_total": len(self.groq_api_keys),
            "groq_keys_active": len(self.groq_api_keys) - len(self.groq_failed_keys),
            "groq_failed_keys": list(self.groq_failed_keys),
        }


# ============================================
# Singleton
# ============================================
_llm_manager: Optional[MultiKeyGroqChat] = None


def get_llm_manager() -> MultiKeyGroqChat:
    """Get or create the singleton LLM manager."""
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = MultiKeyGroqChat()
    return _llm_manager


def get_chat_llm() -> BaseChatModel:
    """Get a chat LLM instance ready for use with LangGraph."""
    manager = get_llm_manager()
    return manager.get_llm()


def get_llm_with_tools(tools: list) -> BaseChatModel:
    """Get a LLM instance with tools bound."""
    llm = get_chat_llm()
    return llm.bind_tools(tools)
