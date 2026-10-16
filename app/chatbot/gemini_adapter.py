"""Cloud Gemini Adapter Interface.

Connects to Google Cloud Gemini models (e.g., gemini-2.5-flash, gemini-2.0-flash)
for dynamic script generation, parameter extraction, and scientific reasoning.
"""
import logging
import os
from typing import Optional, Dict, Any, List, Tuple
from app.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger("gemini_pipeline")

class CloudGeminiClient:
    """Agentic adapter for Google Cloud Gemini models (gemini-2.5-flash)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        self.api_key = (api_key if api_key is not None else GEMINI_API_KEY).strip()
        self.model_name = (model_name if model_name is not None else GEMINI_MODEL).strip()
        if not self.model_name:
            self.model_name = "gemini-2.5-flash"
        self.last_error: Optional[str] = None
        self._client = None

    def set_api_key(self, api_key: str, model_name: Optional[str] = None) -> None:
        """Dynamically updates the Gemini API key and model at runtime."""
        self.api_key = api_key.strip()
        if model_name:
            self.model_name = model_name.strip()
        self._client = None
        self.last_error = None

    def is_configured(self) -> bool:
        """Checks if a non-placeholder Gemini API key is configured."""
        if not self.api_key:
            return False
        if "your_gemini_api_key_here" in self.api_key:
            return False
        return len(self.api_key) > 10

    def is_available(self) -> bool:
        """Returns True if the client has an API key configured."""
        return self.is_configured()

    def _get_client(self):
        """Initializes or returns the google.genai Client."""
        if self._client is not None:
            return self._client

        if not self.is_configured():
            raise ValueError("No valid GEMINI_API_KEY configured.")

        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
            return self._client
        except Exception as e:
            logger.warning("google.genai initialization failed, attempting fallback: %s", e)
            try:
                import google.generativeai as legacy_genai
                legacy_genai.configure(api_key=self.api_key)
                self._client = legacy_genai.GenerativeModel(self.model_name)
                return self._client
            except Exception as e2:
                raise RuntimeError(f"Failed to initialize Gemini client: {e2}")

    def generate_with_diagnostics(
        self,
        prompt: str,
        system_context: str = "",
        rag_context: Optional[List[str]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        extracted_params: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Invokes Cloud Gemini with structured liquid-state physics prompt and returns (response_text, error_message)."""
        if not self.is_configured():
            err = (
                "Gemini API key is not configured. "
                "Please set GEMINI_API_KEY in .env or provide it in the UI settings. "
                "Get a free API key at https://aistudio.google.com/apikey"
            )
            self.last_error = err
            return None, err

        # 1. System Prompt & Liquid Physics Guardrails
        default_system = (
            "You are an expert computational physicist and LAMMPS molecular dynamics specialist.\n"
            "Your specialization is strictly in LIQUID-STATE simulations and transport properties:\n"
            "- Lennard-Jones fluids (units lj, NVE/NVT)\n"
            "- Rigid SPC/E liquid water (units real, pair_style lj/cut/coul/long with PPPM kspace_style 1e-4, fix shake)\n"
            "- Molten metals (units metal, EAM potentials such as Ni_u3.eam, Al_zhou.eam.alloy, post-melt liquid thermalization)\n"
            "- Liquid transport properties: Self-diffusion coefficient (Einstein relation via compute msd), shear viscosity (equilibrium Green-Kubo via compute stress/atom or fix ave/correlate), and Radial Distribution Function (compute rdf).\n\n"
            "Instructions for simulation requests:\n"
            "1. Output a complete, valid, runnable LAMMPS script enclosed in a single ```lammps ... ``` code block.\n"
            "2. Strictly obey the user's requested parameters (temperatures, atom counts, quench rates, ensembles, timesteps, dump frequencies). Never override user temperatures with arbitrary defaults.\n"
            "3. Structure the script properly: units, boundary, atom_style, lattice/region/box, potential, minimization, thermalization/equilibration, and production run.\n"
            "4. Provide a clear Markdown explanation detailing the physics, ensemble choice, and potential parameters."
        )
        sys_instructions = system_context.strip() if system_context else default_system

        # 2. Build User Content with Extracted Parameters & RAG Context
        user_parts = []
        if conversation_history:
            history_lines = []
            for turn in conversation_history[-3:]:
                u = turn.get("user", "")
                a = turn.get("assistant", "")
                if u:
                    history_lines.append(f"User: {u[:200]}")
                if a:
                    # Truncate assistant history to avoid context bloat
                    history_lines.append(f"Assistant: {a[:250]}")
            if history_lines:
                user_parts.append("### CONVERSATION HISTORY\n" + "\n".join(history_lines))

        if extracted_params:
            params_lines = [f"- {k}: {v}" for k, v in extracted_params.items() if v is not None]
            if params_lines:
                user_parts.append("### EXTRACTED USER SIMULATION PARAMETERS\n" + "\n".join(params_lines))

        if rag_context:
            compact_rag = "\n".join([f"- {c[:300].strip()}" for c in rag_context[:4]])
            user_parts.append(f"### AUTHORITATIVE LAMMPS & WORKSPACE DOCUMENTATION CONTEXT\n{compact_rag}")

        user_parts.append(f"### USER INQUIRY\n{prompt}\n\nPlease generate your expert scientific explanation and custom executable LAMMPS script:")
        full_content = "\n\n".join(user_parts)

        # 3. Call Gemini
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            config = types.GenerateContentConfig(
                system_instruction=sys_instructions,
                temperature=0.2,
                max_output_tokens=2048,
            )
            response = client.models.generate_content(
                model=self.model_name,
                contents=full_content,
                config=config
            )
            resp_text = (response.text or "").strip()
            if resp_text:
                self.last_error = None
                return resp_text, None
            else:
                err = f"Gemini ({self.model_name}) returned an empty response."
                self.last_error = err
                return None, err

        except Exception as e:
            err_str = str(e)
            logger.error("Gemini invocation failed: %s", err_str, exc_info=True)
            if "API_KEY_INVALID" in err_str or "API key not valid" in err_str:
                diagnostic = (
                    f"Invalid Gemini API Key. Please verify your GEMINI_API_KEY in .env or UI settings. "
                    f"You can generate a valid free key at https://aistudio.google.com/apikey (Error details: {err_str[:120]})"
                )
            elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                diagnostic = f"Gemini quota exceeded or rate limit reached: {err_str[:150]}"
            else:
                diagnostic = f"Gemini API request error ({type(e).__name__}): {err_str[:200]}"
            
            self.last_error = diagnostic
            return None, diagnostic
