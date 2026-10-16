#!/usr/bin/env python3
"""CLI Diagnostic Utility for checking local LAMMPS installation and GPU/CPU features."""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.lammps.detector import detect_lammps

def main():
    print("==================================================")
    print("   LAMMPS AI Assistant — Local Binary Diagnostic")
    print("==================================================")
    
    detection = detect_lammps()
    print(f"Status: {detection.get('status_text')}")
    print(f"Detected: {detection.get('detected')}")
    print(f"Executable Path: {detection.get('executable')}")
    print(f"Version: {detection.get('version')}")
    
    packages = detection.get('packages', [])
    print(f"Installed Packages ({len(packages)}): {', '.join(packages) if packages else 'None'}")
    print("==================================================")

if __name__ == "__main__":
    main()
