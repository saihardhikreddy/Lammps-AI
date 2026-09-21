"""Local LLM Adapter Interface (Connects to Local Ollama Gemma 4 / LM-Studio)."""
import urllib.request
import json
import time
from typing import Optional, Dict, Any, List
from app.config import OLLAMA_URL, OLLAMA_TAGS_URL, OLLAMA_MODEL

class LocalLLM:
    """Agentic adapter for local language models (Ollama Gemma 4 / LM Studio).
    
    Operates 100% locally on your machine without cloud connections.
    """

    def __init__(self, ollama_url: str = OLLAMA_URL, model_name: str = OLLAMA_MODEL, cache_ttl: float = 10.0):
        self.ollama_url = ollama_url
        self.tags_url = OLLAMA_TAGS_URL
        self.model_name = model_name
        self.cache_ttl = cache_ttl
        self._cached_available: Optional[bool] = None
        self._last_check_time: float = 0.0

    def is_available(self) -> bool:
        """Checks if local Ollama server is actively running on localhost and resolves active model tag."""
        now = time.time()
        if self._cached_available is not None and (now - self._last_check_time) < self.cache_ttl:
            return self._cached_available

        self._last_check_time = now
        try:
            req = urllib.request.Request(self.tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    if models:
                        gemma_matches = [m for m in models if "gemma" in m.lower()]
                        if gemma_matches:
                            self.model_name = gemma_matches[0]
                        elif not any(self.model_name == m for m in models):
                            self.model_name = models[0]
                    self._cached_available = True
                    return True
        except Exception:
            pass

        self._cached_available = False
        return False

    def generate(self, prompt: str, system_context: str = "", rag_context: Optional[List[str]] = None, conversation_history: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
        """Queries local Ollama instance with RAG context and user inquiry formatted specifically for Gemma."""
        if not self.is_available():
            return None

        prompt_parts = []

        if rag_context:
            compact_rag = "\n".join([f"- {c[:180].strip()}" for c in rag_context[:2]])
            prompt_parts.append(f"Using this authoritative LAMMPS reference:\n{compact_rag}")

        if conversation_history:
            history_lines = []
            for turn in conversation_history[-2:]:
                u = turn.get("user", "")
                a = turn.get("assistant", "")
                if u: history_lines.append(f"User: {u[:80]}")
                if a: history_lines.append(f"Assistant: {a[:80]}")
            if history_lines:
                prompt_parts.append("Recent Context:\n" + "\n".join(history_lines))

        prompt_parts.append(f"User Question: {prompt}\n\nPlease provide a clear, conversational, expert scientific explanation in Markdown (with valid ```lammps ... ``` code blocks if generating or fixing simulation scripts):")

        full_prompt = "\n\n".join(prompt_parts)

        try:
            payload = {
                "model": self.model_name,
                "prompt": full_prompt,
                "stream": False
            }
            req = urllib.request.Request(
                self.ollama_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=45.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                resp_text = data.get("response", "").strip()
                return resp_text if resp_text else None
        except Exception:
            return None
