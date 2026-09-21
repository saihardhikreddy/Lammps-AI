"""Data schemas for knowledge retrieval and document chunking."""
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class DocChunk:
    """Represents a chunk of indexed LAMMPS documentation."""
    chunk_id: str
    source_path: str
    doc_type: str
    section: str
    subsection: str
    command_name: Optional[str] = None
    title: str = ""
    content: str = ""
    keywords: List[str] = field(default_factory=list)

@dataclass
class ExampleChunk:
    """Represents a validated LAMMPS example script chunk."""
    example_id: str
    topic: str = ""
    title: str = ""
    category: str = ""
    description: str = ""
    script: str = ""
    script_content: str = ""
    materials: List[str] = field(default_factory=list)
    commands_used: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.script_content and self.script:
            self.script_content = self.script
        if not self.script and self.script_content:
            self.script = self.script_content
        if not self.topic and self.title:
            self.topic = self.title
