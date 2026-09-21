"""Central Conversational AI Router, Master Dispatcher, and Multi-Turn Reasoner with Local Gemma 4 & Project Workspace RAG."""
import uuid
import re
from typing import Dict, Any, Optional, List
from app.knowledge.retriever import LocalKnowledgeRetriever
from app.knowledge.workspace_indexer import WorkspaceProjectIndexer
from app.generation.intent import IntentExtractor
from app.generation.generator import ScriptGenerator
from app.lammps.validator import ScriptValidator
from app.lammps.error_analyzer import ErrorAnalyzer
from app.lammps.parser import ThermoParser
from app.chatbot.memory import ConversationMemory
from app.chatbot.responder import MarkdownResponder
from app.chatbot.llm_adapter import LocalLLM
from app.chatbot.conversational_ai import ConversationalEngine

class ChatbotRouter:
    """Master conversational reasoning engine for local LAMMPS assistance, guidance, and project codebase RAG."""

    def __init__(self):
        self.retriever = LocalKnowledgeRetriever()
        self.workspace_indexer = WorkspaceProjectIndexer()
        self.intent_extractor = IntentExtractor()
        self.generator = ScriptGenerator(self.retriever)
        self.validator = ScriptValidator()
        self.error_analyzer = ErrorAnalyzer(self.retriever)
        self.thermo_parser = ThermoParser()
        self.memory = ConversationMemory()
        self.responder = MarkdownResponder()
        self.local_llm = LocalLLM()
        self.conversational_engine = ConversationalEngine()

    def open_workspace(self, folder_path: str) -> Dict[str, Any]:
        """Loads and indexes a project directory into the active workspace RAG index."""
        return self.workspace_indexer.open_workspace(folder_path)

    def process_message(self, conversation_id: Optional[str], message: str) -> Dict[str, Any]:
        if not conversation_id or not conversation_id.strip():
            conversation_id = str(uuid.uuid4())

        msg_lower = message.lower().strip()

        response_payload = {
            "conversation_id": conversation_id,
            "intent": "GENERAL_CONVERSATION",
            "answer": "",
            "script": None,
            "validation": None,
            "citations": [],
            "assumptions": [],
            "requires_confirmation": False
        }

        # ── PRIORITY 1: Short conversational inputs (greetings, help, bye) ─
        is_short_input = len(msg_lower.split()) <= 4
        is_greeting_or_meta = bool(re.search(
            r"\b(hi|hello|hey|help|bye|goodbye|thanks|thank|who are you|your name|what are you)\b",
            msg_lower
        ))

        if is_short_input and is_greeting_or_meta:
            conv_match = self.conversational_engine.match_intent(message)
            if conv_match:
                response_payload["intent"] = conv_match["intent"]
                response_payload["answer"] = conv_match["answer"]
                response_payload["citations"] = conv_match.get("citations", [])
                self.memory.save_turn(conversation_id, message, response_payload)
                return response_payload

        # ── PRIORITY 2: Error Message Diagnosis ────────────────────────────
        if any(w in msg_lower for w in ["error:", "illegal", "lost atoms", "cannot open", "out of range atoms"]):
            err_diag = self.error_analyzer.analyze(message)
            answer_text = (
                f"**Identified Command**: `{err_diag['identified_command']}`\n\n"
                f"**Probable Cause**:\n{err_diag['probable_cause']}\n\n"
                f"**Scientific Rationale**:\n{err_diag['scientific_reason']}\n\n"
                f"**Recommended Fix**:\n{err_diag['suggested_fix']}"
            )
            response_payload["intent"] = "DIAGNOSE_ERROR"
            response_payload["answer"] = self.responder.format_technical_answer(
                answer=answer_text,
                command_syntax=err_diag.get("patch_example"),
                why_explanation="Applying physical constraints, stable timesteps, or explicit minimization prevents divergence in numerical time integration.",
                citations=err_diag["documentation_citations"],
                example_snippet=err_diag.get("patch_example"),
                notes="Ensure initial configuration has zero particle overlaps before launching long MD runs."
            )
            response_payload["citations"] = err_diag["documentation_citations"]
            self.memory.save_turn(conversation_id, message, response_payload)
            return response_payload

        # ── PRIORITY 3: Pasted Broken Script Auto-Repair ───────────────────
        known_cmds = {
            "units", "atom_style", "boundary", "lattice", "region", "create_box",
            "create_atoms", "mass", "pair_style", "pair_coeff", "velocity", "fix",
            "unfix", "timestep", "thermo", "thermo_style", "run", "minimize",
            "neigh_modify", "neighbor", "kspace_style", "dump", "variable"
        }
        script_lines = [l.strip() for l in message.splitlines() if l.strip() and not l.strip().startswith('#')]
        matching_cmd_lines = sum(1 for line in script_lines if line.split()[0].lower() in known_cmds)
        is_pasted_script = ("\n" in message) and (matching_cmd_lines >= 2)

        if is_pasted_script:
            val_res = self.validator.validate_static(message)
            if not val_res["valid"] or val_res["warnings"]:
                repaired_script, applied_fixes = self._repair_script(message, val_res)
                repaired_val = self.validator.validate_static(repaired_script)

                err_list = "\n".join([f"- **Error**: {e}" for e in val_res["errors"]]) if val_res["errors"] else "- None detected"
                warn_list = "\n".join([f"- **Warning**: {w}" for w in val_res["warnings"]]) if val_res["warnings"] else "- None detected"
                fixes_list = "\n".join([f"- {f}" for f in applied_fixes]) if applied_fixes else "- Verified baseline syntax"

                answer = (
                    "### Script Analysis & Automatic Fix\n\n"
                    "I analyzed your script and detected the following issues:\n\n"
                    f"{err_list}\n"
                    f"{warn_list}\n\n"
                    "### Applied Corrections\n\n"
                    f"{fixes_list}\n\n"
                    "### Corrected & Executable Script\n\n"
                    f"```lammps\n{repaired_script}\n```"
                )
                response_payload["intent"] = "REPAIR_SCRIPT"
                response_payload["answer"] = answer
                response_payload["script"] = repaired_script
                response_payload["validation"] = repaired_val
                response_payload["requires_confirmation"] = repaired_val["valid"]
                response_payload["citations"] = ["LAMMPS Manual -> Commands", "LAMMPS Manual -> Errors & Troubleshooting"]
                self.memory.save_turn(conversation_id, message, response_payload)
                return response_payload

        # ── PRIORITY 4: Simulation Script Generation ───────────────────────
        spec = self.intent_extractor.extract_intent(message)
        if spec["intent"] == "GENERATE_SCRIPT":
            response_payload["intent"] = "GENERATE_SCRIPT"
            missing = spec.get("missing_parameters", [])
            if missing and not spec.get("material_name"):
                missing_list = "\n".join([f"- **{m}**" for m in missing])
                answer_text = (
                    f"To generate a tailored simulation for your experiment, please specify:\n\n"
                    f"{missing_list}\n\n"
                    f"*(For example: 'Simulate melting of aluminum at 900 K' or 'Create a Lennard-Jones liquid simulation')*"
                )
                response_payload["answer"] = self.responder.format_technical_answer(
                    answer=answer_text,
                    citations=["LAMMPS Manual -> Section 3 -> Commands", "LAMMPS Manual -> Potential Styles"],
                    notes="Explicitly defining atom types and boundary conditions ensures correct physics."
                )
                response_payload["citations"] = ["LAMMPS Manual -> Commands", "LAMMPS Manual -> Examples"]
            else:
                gen_res = self.generator.generate(spec)
                script = gen_res["script"]
                val_res = self.validator.validate_static(script)

                assump_md = "\n".join([f"- {a}" for a in gen_res["assumptions"]])
                answer_text = (
                    f"**Goal**: {gen_res['goal']}\n\n"
                    f"### Key Assumptions & Parameters\n{assump_md}\n\n"
                    f"### Ready to Simulate Locally\n"
                    f"Click **'Run Simulation Locally'** below to execute this simulation on your installed LAMMPS binary."
                )

                response_payload["answer"] = self.responder.format_technical_answer(
                    answer=answer_text,
                    command_syntax=f"# Generated LAMMPS Script\n{script}",
                    why_explanation="Selected potential styles, thermostats, and timesteps are matched to the material lattice and unit system for numeric stability.",
                    citations=gen_res["citations"],
                    notes=gen_res["limitations"]
                )
                response_payload["script"] = script
                response_payload["validation"] = val_res
                response_payload["assumptions"] = gen_res["assumptions"]
                response_payload["citations"] = gen_res["citations"]
                response_payload["requires_confirmation"] = val_res["valid"]

            self.memory.save_turn(conversation_id, message, response_payload)
            return response_payload

        # ── PRIORITY 5: Agentic Local LLM with Project Workspace & Manual RAG ─
        # When Gemma / Ollama is active on the machine, query Gemma with both
        # Project Codebase chunks (if workspace is open) and LAMMPS manual chunks!
        if self.local_llm.is_available():
            rag_docs = []
            citations = []

            # 1. Search Active Project Workspace
            if self.workspace_indexer.is_active():
                proj_results = self.workspace_indexer.search_workspace(message, top_k=2)
                for chunk, score in proj_results:
                    rag_docs.append(
                        f"Workspace File: {chunk.rel_path} (Lines {chunk.start_line}-{chunk.end_line}) [{chunk.block_type}]:\n{chunk.content.strip()}"
                    )
                    citations.append(f"Workspace Project → {chunk.rel_path}:{chunk.start_line}-{chunk.end_line}")

            # 2. Search Official LAMMPS Documentation
            search_results = self.retriever.search(message, top_k=2)
            if search_results:
                rag_docs.extend([r[0].content for r in search_results])
                citations.extend([r[0].source_path for r in search_results])

            history = self.memory.get_conversation_history(conversation_id)

            llm_reply = self.local_llm.generate(
                prompt=message,
                rag_context=rag_docs,
                conversation_history=history
            )

            if llm_reply and len(llm_reply.strip()) > 5:
                response_payload["answer"] = llm_reply
                response_payload["source"] = f"Gemma 4 ({self.local_llm.model_name})"
                response_payload["citations"] = citations

                # Check if Gemma returned an executable LAMMPS code block
                code_match = re.search(r"```(?:lammps)?\n(.*?)```", llm_reply, re.DOTALL | re.IGNORECASE)
                if code_match:
                    extracted_code = code_match.group(1).strip()
                    if "\n" in extracted_code and any(k in extracted_code for k in ["units", "atom_style", "pair_style", "fix"]):
                        val_res = self.validator.validate_static(extracted_code)
                        response_payload["script"] = extracted_code
                        response_payload["validation"] = val_res
                        response_payload["requires_confirmation"] = val_res["valid"]

                self.memory.save_turn(conversation_id, message, response_payload)
                return response_payload

        # ── PRIORITY 6: Documentation Search Fallback ──────────────────────
        search_results = self.retriever.search(message, top_k=3)
        if search_results and search_results[0][1] > 0.15:
            top_chunk, score, _ = search_results[0]
            citations = [r[0].source_path for r in search_results]
            ex = self.retriever.find_relevant_example(message)
            ex_code = ex.script_content if ex else None

            response_payload["answer"] = self.responder.format_technical_answer(
                answer=top_chunk.content,
                command_syntax=top_chunk.command_name or top_chunk.title,
                why_explanation=f"Referenced from official LAMMPS documentation section: '{top_chunk.section}'.",
                citations=citations,
                example_snippet=ex_code,
                notes="Ensure the chosen command style is compatible with your active unit convention and atom_style."
            )
            response_payload["citations"] = citations
            self.memory.save_turn(conversation_id, message, response_payload)
            return response_payload

        # ── PRIORITY 7: Conversational Engine Fallback ─────────────────────
        conv_match = self.conversational_engine.match_intent(message)
        if conv_match:
            response_payload["intent"] = conv_match["intent"]
            response_payload["answer"] = conv_match["answer"]
            response_payload["citations"] = conv_match.get("citations", [])
            self.memory.save_turn(conversation_id, message, response_payload)
            return response_payload

        # ── PRIORITY 8: Intelligent Fallback ───────────────────────────────
        user_words = message.strip()
        if len(user_words) < 15:
            answer_text = (
                "I'd be happy to help with that!\n\n"
                "Here are some things I can do for you right now:\n\n"
                "**Quick Actions:**\n"
                "- Say *\"help\"* to see everything I can do\n"
                "- Say *\"simulate melting of aluminum\"* to generate a full simulation\n"
                "- Say *\"what is molecular dynamics?\"* to learn the fundamentals\n"
                "- Open a project folder to index and reason over all your research scripts\n"
                "- Paste any LAMMPS script or error for instant debugging\n\n"
                "I understand natural language, so just ask your question however feels natural!"
            )
        else:
            answer_text = (
                "Thanks for your question. Let me help you with that.\n\n"
                "Based on what you've described, here are some relevant directions:\n\n"
                "- **If this is about a simulation**, tell me the material "
                "(e.g. Aluminum, Copper, Silicon) and what you want to observe "
                "(melting, tensile test, diffusion, thermal conductivity)\n"
                "- **If this is about a LAMMPS command**, try asking directly: "
                "*\"How does fix nvt work?\"* or *\"Explain pair_style eam\"*\n"
                "- **If you have an open project**, ask me about your specific scripts, potentials, or data files\n"
                "- **If you have an error or script**, paste it and I'll diagnose "
                "the issue and give you the corrected version\n\n"
                "Could you provide a bit more detail so I can give you a targeted answer?"
            )
        response_payload["answer"] = answer_text
        response_payload["citations"] = []

        self.memory.save_turn(conversation_id, message, response_payload)
        return response_payload

    def _repair_script(self, broken_script: str, validation_res: Dict[str, Any]) -> tuple[str, list[str]]:
        """Intelligently fixes syntax and missing parameters in a user-pasted script, returning (repaired_script, list_of_applied_fixes)."""
        raw_lines = [line.strip() for line in broken_script.splitlines()]
        clean_lines = [l.split('#')[0].strip() for l in raw_lines]

        has_units = any(l.startswith("units") for l in clean_lines if l)
        has_atom_style = any(l.startswith("atom_style") for l in clean_lines if l)
        has_boundary = any(l.startswith("boundary") for l in clean_lines if l)
        has_run_or_min = any(l.startswith("run ") or l == "run" or l.startswith("minimize ") or l == "minimize" for l in clean_lines if l)
        has_thermo = any(l.startswith("thermo") for l in clean_lines if l)

        is_metal = any("metal" in l or "eam" in l or "Al" in l or "Cu" in l for l in clean_lines if l)
        unit_str = "units metal" if is_metal else "units lj"

        applied_fixes = []
        repaired = []

        if not has_units:
            repaired.append(unit_str)
            applied_fixes.append(f"Added missing '{unit_str}' declaration")
        if not has_boundary:
            repaired.append("boundary p p p")
            applied_fixes.append("Added explicit 'boundary p p p' conditions")
        if not has_atom_style:
            repaired.append("atom_style atomic")
            applied_fixes.append("Added 'atom_style atomic' declaration")

        for line in raw_lines:
            stripped = line.split('#')[0].strip()
            if stripped.startswith("timestep"):
                tokens = stripped.split()
                try:
                    val = float(tokens[1])
                    if is_metal and val > 0.002:
                        repaired.append("timestep 0.001 # Corrected to safe 1 fs step")
                        applied_fixes.append(f"Reduced unsafe timestep ({val} ps) to safe 0.001 ps for metal units")
                        continue
                except Exception:
                    pass
            repaired.append(line)

        if not has_thermo:
            repaired.append("thermo 50")
            applied_fixes.append("Added thermo output frequency ('thermo 50')")
        if not has_run_or_min:
            repaired.append("run 1000")
            applied_fixes.append("Added missing execution directive ('run 1000')")

        return "\n".join(repaired), applied_fixes
