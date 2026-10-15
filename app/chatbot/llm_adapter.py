"""Local LLM Adapter Interface (Connects to Local Ollama Gemma 4 / LM-Studio).

Operates 100% locally on user machine without cloud connections.
Uses Ollama /api/chat with structured system and user messages.
"""
import urllib.request
import json
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from app.config import OLLAMA_TAGS_URL, OLLAMA_MODEL

logger = logging.getLogger("llm_pipeline")

class LocalLLM:
    """Agentic adapter for local language models (Ollama Gemma 4 / LM Studio).
    
    Operates 100% locally on your machine without cloud connections.
    """

    def __init__(
        self,
        chat_url: str = "http://127.0.0.1:11434/api/chat",
        tags_url: str = OLLAMA_TAGS_URL,
        model_name: str = OLLAMA_MODEL,
        cache_ttl: float = 10.0
    ):
        self.chat_url = chat_url
        self.tags_url = tags_url
        self.model_name = model_name
        self.cache_ttl = cache_ttl
        self._cached_available: Optional[bool] = None
        self._last_check_time: float = 0.0
        self.last_error: Optional[str] = None

    def is_available(self) -> bool:
        """Checks if local Ollama server is actively running on 127.0.0.1:11434 and resolves active model tag."""
        now = time.time()
        if self._cached_available is not None and (now - self._last_check_time) < self.cache_ttl:
            return self._cached_available

        self._last_check_time = now
        try:
            req = urllib.request.Request(self.tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=2.5) as resp:
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
                    self.last_error = None
                    return True
        except Exception as e:
            self.last_error = f"Ollama not reachable at {self.tags_url}: {e}"
            logger.debug("Ollama availability check failed: %s", e)

        self._cached_available = False
        return False

    def generate(
        self,
        prompt: str,
        system_context: str = "",
        rag_context: Optional[List[str]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        extracted_params: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Queries local Ollama instance with RAG context and user inquiry."""
        text, _ = self.generate_with_diagnostics(
            prompt=prompt,
            system_context=system_context,
            rag_context=rag_context,
            conversation_history=conversation_history,
            extracted_params=extracted_params
        )
        return text

    def generate_with_diagnostics(
        self,
        prompt: str,
        system_context: str = "",
        rag_context: Optional[List[str]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        extracted_params: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Queries local Ollama instance using /api/chat with structured system and user messages.
        
        Guarantees transparent error reporting without silently masking failures behind static mocks.
        """
        if not self.is_available():
            err = self.last_error or "Local Ollama daemon is offline (127.0.0.1:11434 unreachable)."
            logger.warning("Local LLM invocation aborted: %s", err)
            return None, err

        # 1. System Prompt & Guardrails
        default_system = (
            "You are an expert computational physicist and LAMMPS molecular dynamics specialist.\n"
            "Your specialization is strictly in LIQUID-STATE simulations and transport properties (e.g., molten metals, SPC/E liquid water, Lennard-Jones fluids, self-diffusion, shear viscosity, RDF).\n"
            "Instructions for simulation requests:\n"
            "1. Output a complete, runnable LAMMPS script enclosed in a single ```lammps ... ``` code block.\n"
            "2. Strictly obey the user's requested parameters (temperatures, atom counts, quench rates, ensembles, timesteps, dump frequencies). Never override user temperatures with arbitrary defaults.\n"
            "3. Structure the script properly: units, boundary, atom_style, box creation/lattice, potential (e.g. eam/alloy with Ni_u3.eam/Al_zhou.eam.alloy, or lj/cut), minimization, thermalization, and production integration.\n"
            "4. Provide a clear Markdown explanation detailing the physics, ensemble choice, and potential parameters."
        )
        sys_instructions = system_context.strip() if system_context else default_system

        messages = [
            {"role": "system", "content": sys_instructions}
        ]

        # 2. Add Recent Conversation History
        if conversation_history:
            for turn in conversation_history[-2:]:
                u = turn.get("user", "")
                a = turn.get("assistant", "")
                if u:
                    messages.append({"role": "user", "content": u[:150]})
                if a:
                    messages.append({"role": "assistant", "content": a[:200]})

        # 3. Assemble User Content with Extracted Parameters & RAG Context
        user_parts = []
        if extracted_params:
            params_lines = [f"- {k}: {v}" for k, v in extracted_params.items() if v is not None]
            if params_lines:
                user_parts.append("### EXTRACTED USER SIMULATION PARAMETERS\n" + "\n".join(params_lines))

        if rag_context:
            compact_rag = "\n".join([f"- {c[:220].strip()}" for c in rag_context[:3]])
            user_parts.append(f"### AUTHORITATIVE LAMMPS DOCUMENTATION CONTEXT\n{compact_rag}")

        user_parts.append(f"### USER PROMPT\n{prompt}\n\nPlease provide your expert scientific explanation and custom executable LAMMPS script:")

        messages.append({"role": "user", "content": "\n\n".join(user_parts)})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": 512,
                "temperature": 0.2,
                "top_p": 0.9
            }
        }

        try:
            req = urllib.request.Request(
                self.chat_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=180.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                msg = data.get("message", {})
                resp_text = (msg.get("content") or msg.get("thinking") or "").strip()
                if resp_text:
                    self.last_error = None
                    return resp_text, None
                else:
                    err = "Local model returned an empty completion."
                    logger.warning(err)
                    self.last_error = err
                    return None, err

        except Exception as e:
            err_msg = f"Local LLM ({self.model_name}) request failed: {type(e).__name__}: {e}"
            logger.error(err_msg, exc_info=True)
            self.last_error = err_msg
            return None, err_msg
