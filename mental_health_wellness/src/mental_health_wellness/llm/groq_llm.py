"""
LangGraph-Compatible LLM Wrapper
Multi-key Groq LLM with automatic rotation on rate limits
"""

import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv()


class MultiKeyGroqChat:
    """
    Manager for multiple Groq API keys with automatic rotation on rate limits.
    """
    
    def __init__(
        self,
        api_keys: Optional[List[str]] = None,
        model: str = "llama-3.1-8b-instant",
        temperature: float = 0.7,
        max_tokens: int = 1024
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Load Groq keys
        self.groq_api_keys = api_keys or self._load_groq_keys()
        self.current_groq_key_idx = 0
        self.groq_failed_keys: set = set()

        # v5.3 OPT-2: Instance cache — reuse ChatGroq objects instead of
        # reconstructing them (with header/client setup) on every pipeline call.
        # Cache keyed by (key_idx, model) and cleared when a key is failed.
        self._llm_cache: Dict[tuple, Any] = {}
        
        if not self.groq_api_keys:
            raise ValueError("No Groq API keys found. Set GROQ_API_KEY or GROQ_API_KEY_1, GROQ_API_KEY_2, etc. in .env")
        
        print(f"[LLM] Initialized Groq Chat Manager with {len(self.groq_api_keys)} keys")

    def _load_groq_keys(self) -> List[str]:
        """
        Load Groq API keys from environment variables.
        Looks for GROQ_API_KEY_1, GROQ_API_KEY_2, etc.
        Falls back to GROQ_API_KEY if numbered keys not found.
        """
        keys = []
        i = 1
        while True:
            key = os.getenv(f"GROQ_API_KEY_{i}")
            if not key:
                break
            keys.append(key)
            i += 1
        
        # Fallback to single GROQ_API_KEY if no numbered keys found
        if not keys:
            key = os.getenv("GROQ_API_KEY")
            if key:
                keys.append(key)
        
        return keys

    def _load_openai_keys(self) -> List[str]:
        """
        Load OpenAI API keys from environment variables.
        Looks for OPENAI_API_KEY_1, OPENAI_API_KEY_2, etc.
        Falls back to OPENAI_API_KEY if numbered keys not found.
        """
        keys = []
        i = 1
        while True:
            key = os.getenv(f"OPENAI_API_KEY_{i}")
            if not key:
                break
            keys.append(key)
            i += 1
        
        # Fallback to single OPENAI_API_KEY if no numbered keys found
        if not keys:
            key = os.getenv("OPENAI_API_KEY")
            if key:
                keys.append(key)
        
        return keys
    
    def _get_available_groq_key_idx(self) -> Optional[int]:
        """Get next valid Groq key index, or None if all failed"""
        for idx in range(len(self.groq_api_keys)):
            if idx not in self.groq_failed_keys:
                return idx
        return None
    
    def get_llm(self, model: Optional[str] = None) -> BaseChatModel:
        """
        Get a Groq LLM instance with automatic key rotation.
        Returns a CACHED instance when the same key+model was used before.
        If all keys are exhausted, resets and tries again.
        """
        key_idx = self._get_available_groq_key_idx()
        
        # If all keys failed, reset and try again
        if key_idx is None:
            print(f"[LLM] ⚠️ All Groq keys exhausted. Resetting...")
            self.groq_failed_keys.clear()
            self._llm_cache.clear()  # Clear cache on full reset
            key_idx = self._get_available_groq_key_idx()
        
        if key_idx is None:
            raise RuntimeError("No valid Groq API keys available")

        effective_model = model or self.model
        cache_key = (key_idx, effective_model)

        if cache_key not in self._llm_cache:
            print(f"[LLM] 🔑 Creating new ChatGroq instance — Key {key_idx + 1}/{len(self.groq_api_keys)} | Model: {effective_model}")
            self._llm_cache[cache_key] = ChatGroq(
                api_key=self.groq_api_keys[key_idx],
                model=effective_model,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
        else:
            print(f"[LLM] ⚡ Reusing cached ChatGroq — Key {key_idx + 1}/{len(self.groq_api_keys)} | Model: {effective_model}")

        return self._llm_cache[cache_key]

    def mark_key_failed(self):
        """Mark current key as failed and rotate to next one."""
        current_idx = self._get_available_groq_key_idx()
        if current_idx is not None:
            self.groq_failed_keys.add(current_idx)
            # Evict cache entries for the failed key across all models
            to_remove = [k for k in self._llm_cache if k[0] == current_idx]
            for k in to_remove:
                del self._llm_cache[k]
            remaining = len(self.groq_api_keys) - len(self.groq_failed_keys)
            print(f"[LLM] ⚠️ Groq Key {current_idx + 1} marked failed. Remaining: {remaining}/{len(self.groq_api_keys)}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of Groq keys"""
        return {
            "groq_keys_total": len(self.groq_api_keys),
            "groq_keys_active": len(self.groq_api_keys) - len(self.groq_failed_keys),
            "groq_failed_keys": list(self.groq_failed_keys),
        }


# Singleton instance
_llm_manager: Optional[MultiKeyGroqChat] = None


def get_llm_manager() -> MultiKeyGroqChat:
    """Get or create the singleton LLM manager"""
    global _llm_manager
    
    if _llm_manager is None:
        _llm_manager = MultiKeyGroqChat()
    
    return _llm_manager


def get_chat_llm() -> BaseChatModel:
    """Get a ChatGroq/OpenAI/Gemini instance ready for use with LangGraph"""
    manager = get_llm_manager()
    return manager.get_llm()


def get_llm_with_tools(tools: list) -> BaseChatModel:
    """Get a LLM instance with tools bound"""
    llm = get_chat_llm()
    return llm.bind_tools(tools)
