"""
LangGraph-Compatible LLM Wrapper — SentiMind v7.0

Provider priority:
  1. Gemini (PRIMARY)   — key rotation across GEMINI_API_KEY_1, _2, etc.
  2. OpenRouter (FALLBACK) — meta-llama/llama-3.3-70b-instruct:free
  3. Groq (LEGACY)      — multi-key pool, only when provider=groq

Usage:
  manager = get_llm_manager()
  llm = manager.get_llm()               # → Gemini (or OpenRouter if Gemini exhausted)
  llm = manager.get_openrouter_llm()    # → OpenRouter directly (for explicit fallback)
"""

import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv()

# ============================================
# MODEL NAME MAPPING
# Translates legacy Groq/LLaMA model names → best OpenRouter equivalents
# ============================================

GROQ_TO_OPENROUTER_MODEL_MAP = {
    # All legacy names → Llama 3.3 70B free (confirmed working on OpenRouter)
    "llama-3.3-70b-versatile":     "meta-llama/llama-3.3-70b-instruct:free",
    "llama-3.1-70b-versatile":     "meta-llama/llama-3.3-70b-instruct:free",
    "llama3-70b-8192":             "meta-llama/llama-3.3-70b-instruct:free",
    "llama-3.1-8b-instant":        "meta-llama/llama-3.3-70b-instruct:free",
    "llama3-8b-8192":              "meta-llama/llama-3.3-70b-instruct:free",
    "mixtral-8x7b-32768":          "meta-llama/llama-3.3-70b-instruct:free",
    "gemma-7b-it":                 "meta-llama/llama-3.3-70b-instruct:free",
}


def _resolve_openrouter_model(model: str) -> str:
    """Map a legacy Groq/model name to its OpenRouter equivalent, or pass through."""
    return GROQ_TO_OPENROUTER_MODEL_MAP.get(model, model)


class MultiKeyGroqChat:
    """
    Unified LLM Manager — 3-tier fallback hierarchy.

    Priority 1 — Gemini (when LLM_PROVIDER=gemini or gemini keys present):
      Uses langchain_google_genai.ChatGoogleGenerativeAI with key rotation.
      Keys: GEMINI_API_KEY_1, GEMINI_API_KEY_2, ... (or GEMINI_API_KEY / GOOGLE_API_KEY)
      Model: GEMINI_MODEL env var (default: gemini-2.5-flash)

    Priority 2 — OpenRouter (when Gemini exhausted or LLM_PROVIDER=openrouter):
      Uses langchain_openai.ChatOpenAI pointed at https://openrouter.ai/api/v1.
      Model: MODEL env var (default: meta-llama/llama-3.3-70b-instruct:free)

    Priority 3 — Groq (legacy fallback, LLM_PROVIDER=groq):
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

        self.provider = "openrouter"

        # ── Gemini (PRIMARY) ─────────────────────────────────────────
        self.gemini_keys = []
        self.gemini_model = ""
        self.gemini_failed_keys: set = set()

        # ── OpenRouter (FALLBACK) ─────────────────────────────────────
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.model = model or os.getenv("MODEL", "meta-llama/llama-3.3-70b-instruct")
        self.model_fast = self.model
        
        if not self.openrouter_api_key:
            print("[LLM] ⚠ WARNING: OPENROUTER_API_KEY not set — fallback may fail")

        # ── Groq (LEGACY LAST RESORT) ─────────────────────────────────
        self.groq_api_keys = []
        self.current_groq_key_idx = 0
        self.groq_failed_keys: set = set()

        # Instance cache keyed by (provider_tag, key_idx, model, reasoning_key)
        self._llm_cache: Dict[tuple, Any] = {}

        # ── Startup banner ─────────────────────────────────────────────
        print("[LLM] ════════════════════════════════════════════════════")
        if False:
            print(f"[LLM]   PRIMARY  : Gemini ({len(self.gemini_keys)} key(s)) | {self.gemini_model}")
        else:
            print("[LLM]   PROVIDER : OpenRouter only")
        print(f"[LLM]   PROVIDER : OpenRouter only | {self.model}")
        if self.groq_api_keys:
            print(f"[LLM]   LEGACY   : Groq ({len(self.groq_api_keys)} key(s))")
        print("[LLM] ════════════════════════════════════════════════════")

    # ------------------------------------------------------------------
    # Key loaders
    # ------------------------------------------------------------------

    def _load_gemini_keys(self) -> List[str]:
        """Load GEMINI_API_KEY_1, _2, ... or fall back to GEMINI_API_KEY / GOOGLE_API_KEY."""
        keys = []
        for i in range(1, 20):
            key = os.getenv(f"GEMINI_API_KEY_{i}")
            if not key:
                break
            keys.append(key)
        if not keys:
            for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                key = os.getenv(env_name)
                if key:
                    keys.append(key)
                    break
        return keys

    def _load_groq_keys(self) -> List[str]:
        """Load GROQ_API_KEY_1, _2, ... or fall back to GROQ_API_KEY."""
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

    # ------------------------------------------------------------------
    # Gemini key management
    # ------------------------------------------------------------------

    def _get_available_gemini_key_idx(self) -> Optional[int]:
        """Return next valid Gemini key index, or None if all exhausted."""
        for idx in range(len(self.gemini_keys)):
            if idx not in self.gemini_failed_keys:
                return idx
        return None

    def mark_gemini_key_failed(self):
        """Mark current Gemini key as rate-limited/failed and rotate to next."""
        current_idx = self._get_available_gemini_key_idx()
        if current_idx is not None:
            self.gemini_failed_keys.add(current_idx)
            # Evict cached instance for this key
            to_remove = [k for k in self._llm_cache if k[0] == "gemini" and k[1] == current_idx]
            for k in to_remove:
                del self._llm_cache[k]
            remaining = len(self.gemini_keys) - len(self.gemini_failed_keys)
            print(f"[LLM] ⚠ Gemini Key {current_idx + 1} failed. Remaining: {remaining}/{len(self.gemini_keys)}")
            if remaining == 0:
                print("[LLM] 🔄 All Gemini keys exhausted → OpenRouter fallback active")

    def reset_gemini_keys(self):
        """Reset all Gemini key failures (e.g. after rate-limit window expires)."""
        self.gemini_failed_keys.clear()
        to_remove = [k for k in self._llm_cache if k[0] == "gemini"]
        for k in to_remove:
            del self._llm_cache[k]
        print(f"[LLM] ✅ Gemini keys reset — {len(self.gemini_keys)} key(s) available")

    # ------------------------------------------------------------------
    # Groq key management (legacy)
    # ------------------------------------------------------------------

    def _get_available_groq_key_idx(self) -> Optional[int]:
        for idx in range(len(self.groq_api_keys)):
            if idx not in self.groq_failed_keys:
                return idx
        return None

    def mark_key_failed(self):
        """Mark current Groq key as failed (legacy compatibility)."""
        current_idx = self._get_available_groq_key_idx()
        if current_idx is not None:
            self.groq_failed_keys.add(current_idx)
            to_remove = [k for k in self._llm_cache if k[1] == current_idx]
            for k in to_remove:
                del self._llm_cache[k]
            remaining = len(self.groq_api_keys) - len(self.groq_failed_keys)
            print(f"[LLM] ⚠ Groq Key {current_idx + 1} marked failed. Remaining: {remaining}/{len(self.groq_api_keys)}")

    # ------------------------------------------------------------------
    # Core: get_llm()  — returns Gemini (primary) or OpenRouter (fallback)
    # ------------------------------------------------------------------

    def get_llm(self, model: Optional[str] = None, reasoning: Optional[dict] = None) -> BaseChatModel:
        """
        Return a ready-to-use LLM instance.

        Priority:
          1. Explicit Groq-only mode (LLM_PROVIDER=groq)
          2. Explicit OpenRouter mode (LLM_PROVIDER=openrouter) — skips Gemini entirely
          3. Gemini  — if GEMINI_API_KEY_* keys available and not all exhausted
          4. OpenRouter — fallback (free Llama 70B)

        Args:
            model:     Hint for OpenRouter model selection (ignored for Gemini).
            reasoning: OpenRouter reasoning config — ignored for Gemini, passed
                       through to OpenRouter if/when falling back.
        """
        # Explicit Groq-only mode
        if False:
            return self._get_groq_llm(model)

        # Explicit OpenRouter mode — skip Gemini entirely
        if True:
            return self._get_openrouter_llm(self.model, reasoning=reasoning)

        # Default: Try Gemini first (LLM_PROVIDER=gemini or unset)
        if False and self.gemini_keys and self._get_available_gemini_key_idx() is not None:
            return self._get_gemini_llm()

        # Gemini unavailable → OpenRouter
        return self._get_openrouter_llm(model, reasoning=reasoning)

    def get_openrouter_llm(self, model: Optional[str] = None, reasoning: Optional[dict] = None) -> BaseChatModel:
        """Always return OpenRouter (for explicit fallback calls)."""
        return self._get_openrouter_llm(model, reasoning=reasoning)

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _get_gemini_llm(self) -> BaseChatModel:
        """Build/cache a ChatGoogleGenerativeAI instance with current key."""
        # pyrefly: ignore [missing-import]
        from langchain_google_genai import ChatGoogleGenerativeAI

        key_idx = self._get_available_gemini_key_idx()
        cache_key = ("gemini", key_idx, self.gemini_model)

        if cache_key not in self._llm_cache:
            print(f"[LLM] ✨ NEW Gemini instance | key={key_idx + 1}/{len(self.gemini_keys)} | model={self.gemini_model}")
            try:
                self._llm_cache[cache_key] = ChatGoogleGenerativeAI(
                    model=self.gemini_model,
                    google_api_key=self.gemini_keys[key_idx],
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                    streaming=True,
                    # convert_system_message_to_human removed — deprecated in v4+
                )
            except Exception as e:
                print(f"[LLM] ❌ Gemini instance creation FAILED | key={key_idx + 1} | error: {e}")
                raise
        else:
            print(f"[LLM] ⚡ Cached Gemini instance | key={key_idx + 1}/{len(self.gemini_keys)} | model={self.gemini_model}")

        return self._llm_cache[cache_key]

    def _get_openrouter_llm(self, model: Optional[str] = None, reasoning: Optional[dict] = None) -> BaseChatModel:
        """Build/cache a ChatOpenAI instance pointed at OpenRouter."""
        from langchain_openai import ChatOpenAI

        if not self.openrouter_api_key:
            raise ValueError("[LLM] ❌ OPENROUTER_API_KEY not configured. Set OPENROUTER_API_KEY in .env")

        raw_model = self.model
        effective_model = _resolve_openrouter_model(raw_model)

        # Include reasoning in cache key to avoid collision between modes
        reasoning_key = str(reasoning) if reasoning is not None else "none"
        cache_key = ("openrouter", 0, effective_model, reasoning_key)

        if cache_key not in self._llm_cache:
            print(f"[LLM] ✨ NEW OpenRouter instance | model={effective_model}")
            print(f"[LLM]    Base URL: {self.openrouter_base_url}")
            print(f"[LLM]    API Key: {'***' + self.openrouter_api_key[-8:]}")

            # NOTE: reasoning param is NOT passed to model_kwargs —
            # Llama 3.3 70B doesn't support it, it causes a LangChain UserWarning.
            # If a reasoning-capable model is configured in future, re-enable here.

            try:
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
            except Exception as e:
                print(f"[LLM] ❌ Failed to create OpenRouter instance: {e}")
                raise
        else:
            print(f"[LLM] ⚡ Cached OpenRouter instance | model={effective_model}")

        return self._llm_cache[cache_key]

    def _get_groq_llm(self, model: Optional[str] = None) -> BaseChatModel:
        """Build/cache a ChatGroq instance with key rotation (legacy fallback path)."""
        from langchain_groq import ChatGroq

        key_idx = self._get_available_groq_key_idx()

        if key_idx is None:
            print("[LLM] ⚠ All Groq keys exhausted. Resetting...")
            self.groq_failed_keys.clear()
            self._llm_cache.clear()
            key_idx = self._get_available_groq_key_idx()

        if key_idx is None:
            raise RuntimeError("No valid Groq API keys available")

        effective_model = model or self.model
        cache_key = ("groq", key_idx, effective_model)

        if cache_key not in self._llm_cache:
            print(f"[LLM] ✨ NEW Groq instance | key={key_idx + 1}/{len(self.groq_api_keys)} | model={effective_model}")
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
        return {
            "provider": self.provider,
            "gemini_keys_total": len(self.gemini_keys),
            "gemini_keys_active": len(self.gemini_keys) - len(self.gemini_failed_keys),
            "gemini_model": self.gemini_model,
            "openrouter_model": self.model,
            "openrouter_key_set": bool(self.openrouter_api_key),
            "groq_keys_total": len(self.groq_api_keys),
            "groq_keys_active": len(self.groq_api_keys) - len(self.groq_failed_keys),
        }


# ============================================
# Async helper — Gemini → OpenRouter fallback
# ============================================

async def invoke_llm(
    messages,
    model: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """
    Invoke LLM with automatic Gemini → OpenRouter fallback.

    Usage:
        from ..llm.groq_llm import invoke_llm
        raw = await invoke_llm([HumanMessage(content=prompt)], max_tokens=200)

    Returns content string. Raises RuntimeError only if both tiers fail.
    """
    import logging
    _logger = logging.getLogger(__name__)
    manager = get_llm_manager()

    # ────────────────────────────────────────────────────────────────
    # TIER 1 — Gemini with key rotation
    # ────────────────────────────────────────────────────────────────
    if manager.provider != "openrouter" and manager.gemini_keys:
        for _ in range(len(manager.gemini_keys)):
            key_idx = manager._get_available_gemini_key_idx()
            if key_idx is None:
                break
            try:
                llm = manager.get_llm()   # Returns Gemini for current valid key
                llm_bound = llm.bind(max_tokens=max_tokens, temperature=temperature)
                print(f"[LLM] 🟢 invoke_llm: Gemini key={key_idx + 1}/{len(manager.gemini_keys)}")
                response = await llm_bound.ainvoke(messages)
                return response.content
            except Exception as e:
                err_str = str(e).lower()
                if any(x in err_str for x in ("429", "quota", "rate", "resource_exhausted", "too many")):
                    _logger.warning(f"[LLM] ⚠ Gemini key={key_idx + 1} rate-limited → rotating")
                    manager.mark_gemini_key_failed()
                    continue
                else:
                    _logger.warning(f"[LLM] ⚠ Gemini key={key_idx + 1} error: {e} → OpenRouter fallback")
                    manager.mark_gemini_key_failed()
                    break

    # ────────────────────────────────────────────────────────────────
    # TIER 2 — OpenRouter fallback
    # ────────────────────────────────────────────────────────────────
    try:
        if not manager.openrouter_api_key:
            raise RuntimeError("[LLM] OpenRouter fallback disabled: OPENROUTER_API_KEY not configured")
        
        llm = manager.get_openrouter_llm(model=model)
        llm_bound = llm.bind(max_tokens=max_tokens, temperature=temperature)
        eff_model = manager.model
        print(f"[LLM] 🔵 invoke_llm: OpenRouter fallback | model={eff_model}")
        response = await llm_bound.ainvoke(messages)
        return response.content
    except Exception as e:
        error_details = f"\n  Error Type: {type(e).__name__}\n  Details: {str(e)}"
        raise RuntimeError(f"[LLM] OpenRouter Llama 3.3 70B failed:{error_details}") from e


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
