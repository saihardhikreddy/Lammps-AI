#!/usr/bin/env python3
"""Main Entrypoint for Local LAMMPS Research Assistant."""
import sys
from pathlib import Path

# Ensure root directory is on Python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.lammps.detector import detect_lammps
from app.ui.server import start_server

def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("\n" + "=" * 65)
    print("      LOCAL LAMMPS RESEARCH ASSISTANT & SIMULATION CHATBOT")
    print("      Local - Offline - Documentation-Grounded - Simulation-Aware")
    print("=" * 65)

    status = detect_lammps()
    print(f"Status: {status['status_text']}")
    print(f"Engine: Zero-Dependency Stdlib + Cloud Gemini & Liquid Physics RAG")
    print("-" * 65)

    if "--check" in sys.argv or "-c" in sys.argv:
        print(f"Executable: {status.get('executable')}")
        print(f"Version: {status.get('version')}")
        return
    
    start_server()

if __name__ == "__main__":
    main()
