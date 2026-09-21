"""Structured Markdown response formatter for technical LAMMPS answers."""
from typing import List, Optional

class MarkdownResponder:
    """Formats technical LAMMPS guidance into clear, academic, and actionable Markdown."""

    def format_technical_answer(
        self,
        answer: str,
        command_syntax: Optional[str] = None,
        why_explanation: Optional[str] = None,
        citations: Optional[List[str]] = None,
        example_snippet: Optional[str] = None,
        notes: Optional[str] = None
    ) -> str:
        parts = [answer.strip()]

        if command_syntax:
            if command_syntax.startswith("#") or "\n" in command_syntax:
                parts.append(f"\n### Syntax / Script\n```lammps\n{command_syntax.strip()}\n```")
            else:
                parts.append(f"\n**Command Syntax**: `{command_syntax.strip()}`")

        if why_explanation:
            parts.append(f"\n### Scientific & Technical Context\n{why_explanation.strip()}")

        if example_snippet:
            parts.append(f"\n### Relevant Example Snippet\n```lammps\n{example_snippet.strip()}\n```")

        if notes:
            if isinstance(notes, list):
                notes_md = "\n".join([f"- {n}" for n in notes])
                parts.append(f"\n### Best Practices & Limitations\n{notes_md}")
            else:
                parts.append(f"\n### Best Practices & Limitations\n{notes.strip()}")

        if citations:
            c_md = "\n".join([f"- {c}" for c in citations])
            parts.append(f"\n### Official Documentation Citations\n{c_md}")

        return "\n\n".join(parts)

    def format_error_diagnosis(
        self,
        diagnosis: str,
        fixed_script: Optional[str] = None,
        error_context: Optional[str] = None,
        citations: Optional[List[str]] = None
    ) -> str:
        parts = [f"### Error Diagnosis & Root Cause\n{diagnosis.strip()}"]

        if error_context:
            parts.append(f"\n**Observed Error**: `{error_context.strip()}`")

        if fixed_script:
            parts.append(f"\n### Corrected / Patched Script\n```lammps\n{fixed_script.strip()}\n```")

        if citations:
            c_md = "\n".join([f"- {c}" for c in citations])
            parts.append(f"\n### Related Documentation References\n{c_md}")

        return "\n\n".join(parts)
