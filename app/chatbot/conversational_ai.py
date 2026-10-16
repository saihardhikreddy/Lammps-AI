"""Conversational AI intent matcher and dialogue fallback."""
import re
from typing import Dict, Any, Optional

class ConversationalEngine:
    """Handles general greetings, capability queries, and conversational intents."""

    def match_intent(self, message: str) -> Optional[Dict[str, Any]]:
        msg = message.lower().strip()

        # Greetings
        if re.search(r"^(hi|hello|hey|greetings|howdy|good\s+(morning|afternoon|evening))\b", msg):
            return {
                "intent": "GREETING",
                "answer": (
                    "Hello! I am **LAMMPS AI**, your local computational physics and molecular dynamics research assistant.\n\n"
                    "I can assist you with:\n"
                    "- **Input Script Generation**: Setting up NVT/NPT/NVE ensembles, mechanical tensile deformation, melting, or diffusion simulations.\n"
                    "- **Script Doctor & AST Validation**: Pre-flight checks for stable timesteps, periodic boundary conditions, and force field assignments.\n"
                    "- **Runtime Error Diagnosis**: Troubleshooting `Lost atoms`, `Illegal fix`, and unphysical thermodynamic fluctuations.\n"
                    "- **Project Workspace RAG**: Indexing your local simulation directories, data files, and Python pipelines.\n\n"
                    "What molecular simulation would you like to construct or analyze?"
                )
            }

        # Capabilities / Help
        if re.search(r"\b(who are you|what can you do|help|capabilities|features)\b", msg):
            return {
                "intent": "CAPABILITIES",
                "answer": (
                    "### LAMMPS AI Capabilities\n\n"
                    "1. **Script Generation**: Generates complete, physically sound LAMMPS scripts for Lennard-Jones fluids, FCC metals (Al, Cu, Ni), and multi-component systems.\n"
                    "2. **Script Doctor**: Static pre-flight validator detecting dangerous timesteps ($>2\\text{ fs}$ in metal units), missing `pair_coeff`, and unbounded boxes.\n"
                    "3. **Error Analysis**: Automated root cause diagnosis and 1-click script patching for common runtime crashes.\n"
                    "4. **Shah Research Group MDTransport**: Automated transport property calculation ($D_i$, $\\sigma$, $\\eta$, $g(r)$) via MDTransport CLI syntax.\n"
                    "5. **Local RAG & Codebase Search**: Multi-file indexing and semantic search across `.in`, `.data`, `.py`, `.eam` files.\n"
                    "6. **100% Offline & Private**: Zero cloud API tracking, running purely on your local hardware."
                )
            }

        # General physics guidance
        if "what is lammps" in msg or "about lammps" in msg:
            return {
                "intent": "GENERAL_KNOWLEDGE",
                "answer": (
                    "**LAMMPS** (Large-scale Atomic/Molecular Massively Parallel Simulator) is a premier classical molecular dynamics code "
                    "developed by Sandia National Laboratories. It models atomic, polymeric, biological, metallic, and granular systems at "
                    "spatial scales ranging from single atoms to continuum mesoscopic scales."
                )
            }

        return None
