"""Documentation Ingestion Utility for indexing external LAMMPS manual chapters and custom papers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.knowledge.indexer import LocalIndexer
from app.knowledge.schema import DocChunk

def ingest_directory(directory_path: str):
    p = Path(directory_path)
    if not p.exists():
        print(f"Directory not found: {directory_path}")
        return
    
    indexer = LocalIndexer()
    count = 0
    for f in p.glob("**/*"):
        if f.is_file() and f.suffix.lower() in [".txt", ".md", ".html", ".rst"]:
            content = f.read_text(encoding="utf-8", errors="replace")
            chunk = DocChunk(
                chunk_id=f"doc_{f.stem}_{count}",
                source_path=str(f),
                doc_type="manual_chapter",
                section="User Docs",
                subsection=f.stem,
                title=f.name,
                content=content[:4000],
                keywords=f.stem.split("_")
            )
            indexer.save_chunk(chunk)
            count += 1
            
    print(f"Successfully ingested and indexed {count} document chunks into local SQLite vector store.")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent.parent / "data")
    ingest_directory(target)
