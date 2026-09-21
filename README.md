# Local LAMMPS Research Assistant and Simulation Chatbot

> **Subtitle**: Local • Offline • Documentation-Grounded • Simulation-Aware

A high-performance, academic research assistant for molecular dynamics (MD) simulations using **LAMMPS** (Large-scale Atomic/Molecular Massively Parallel Simulator).

---

## 1. Project Overview

The **Local LAMMPS Research Assistant** enables materials scientists, computational chemists, and physics researchers to interact with LAMMPS using natural language. The system is **100% offline and local**, requiring no internet connection, no remote LLM APIs (OpenAI, Anthropic, Gemini, Hugging Face), and no cloud vector databases.

### Core Capabilities:
1. **Command & Syntax Grounding**: Search and retrieve exact syntax from the official LAMMPS manual.
2. **Deterministic Multi-Signal Retrieval**: Transparent keyword, command-name, section, and example matching.
3. **Simulation Requirement Extraction**: Converts natural language prompts into structured specifications.
4. **Script Generation**: Synthesizes complete, validated `.in` scripts grounded in official examples.
5. **Static & Scientific Validation**: Checks unit systems, force fields, timestep stability, and periodic boundary conditions.
6. **Local Execution with Human-in-the-Loop Confirmation**: Safely runs simulations on locally installed LAMMPS binaries (`lmp`, `lmp_serial`, `lmp_mpi`).
7. **Deterministic Output & Thermo Analysis**: Parses `log.lammps`, calculates thermodynamic averages (min, max, mean, drift), and evaluates temperature stability.
8. **Diagnostic Error Analyzer**: Diagnoses errors (e.g. `Lost atoms`, `Illegal fix`, `Out of range atoms`) and suggests grounded code patches.
9. **Late-Binding Research Adapters**: Includes pluggable interface for **Shah Research Group** extensions.

---

## 2. Layered Architecture

```text
┌────────────────────────────────────────────────────────┐
│                   Web Chatbot UI                       │
│    (Vanilla JS + HTML5 + CSS3 + Confirmation Modal)    │
└───────────────────────────▲────────────────────────────┘
                            │ REST API (/api/chat, /api/run, /api/status)
┌───────────────────────────▼────────────────────────────┐
│                    Chatbot Router                      │
│        (Intent Dispatcher & Response Formatter)        │
└─────────┬──────────────┬──────────────┬────────────────┘
          │              │              │
┌─────────▼────────┐ ┌───▼───────────┐ ┌▼────────────────┐
│  Knowledge Base  │ │  Script Gen   │ │ Error Diagnostic│
│  & Multi-Signal  │ │   & Workflow  │ │   & Validation  │
│    Retriever     │ │    Planner    │ │     Engine      │
└─────────┬────────┘ └───┬───────────┘ └┬────────────────┘
          │              │              │
┌─────────▼──────────────▼──────────────▼────────────────┐
│                 Local LAMMPS Engine                    │
│   (Binary Detection, Process Runner, Thermo Parser)   │
└───────────────────────────▲────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│          Pluggable Shah Research Group Adapter         │
└────────────────────────────────────────────────────────┘
```

---

## 3. Minimal Requirements

- **Operating System**: Windows, Linux, or macOS.
- **Python**: Version 3.9+ (Python Standard Library only!).
- **LAMMPS** *(optional for execution)*: `lmp`, `lmp_serial`, `lmp_mpi`, or configured path via `LAMMPS_EXECUTABLE`.

---

## 4. Quick Start (Windows)

### Step 1: Open PowerShell and Navigate to the Project
```powershell
cd local-lammps-assistant
```

### Step 2: Verify System Readiness
```powershell
python scripts\check_lammps.py
```

### Step 3: Run the Test Suite
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

### Step 4: Launch the Local Research Assistant
```powershell
python run.py
```

Open your web browser and navigate to:
```text
http://127.0.0.1:8080
```

---

## 5. Usage Scenarios & Interactive Demos

### Scenario A: Technical Command Question
- **User Prompt**: `"How do I use fix nvt?"` or `"Explain pair_style eam"`
- **Response**: The assistant provides syntax, parameter rules, and exact documentation citations (e.g. `LAMMPS Manual → Commands → fix nvt`).

### Scenario B: Generating an MD Simulation
- **User Prompt**: `"Simulate melting of aluminum using an NVT ensemble"`
- **Assistant Workflow**:
  1. Identifies element (`Al`), lattice (`FCC 4.05 Å`), and potential (`eam/alloy`).
  2. Synthesizes a verified LAMMPS script.
  3. Runs static rule and timestep validation.
  4. Provides scientific assumptions and execution instructions.
  5. Displays a **"▶ Run Simulation Locally"** button.

### Scenario C: Safe Local Execution & Thermo Parsing
1. Click **"Run Simulation Locally"**.
2. Review the confirmation modal and parameters.
3. Click **"Confirm & Run Locally"**.
4. The local LAMMPS binary executes in an isolated directory (`simulations/runs/<run_id>/`).
5. Real-time stdout, runtime seconds, and a thermodynamic statistical summary table (`Step`, `Temp`, `TotEng`, `Press`, `Mean`, `Std Dev`) are rendered.

### Scenario D: Error Diagnostics & Root-Cause Analysis
- **User Prompt**: `"My simulation crashed with: ERROR: Lost atoms: original 1000 current 990"`
- **Response**: Explains that high initial force overlap or large timestep caused numerical divergence, cites `timestep` and `minimize` documentation, and provides a corrected script block.

---

## 6. Offline Knowledge Ingestion

To index additional local manual files or PDFs/HTML pages:
1. Place `.html`, `.rst`, `.txt`, or `.md` files in `data/docs/`.
2. Run the ingestion pipeline:
```powershell
python scripts\ingest_docs.py
```

---

## 7. Shah Research Group Integration

The system includes a dedicated `ResearchPackageAdapter` interface located at `app/adapters/shah_adapter.py`.

```python
from app.adapters.shah_adapter import ResearchPackageAdapter

class CustomShahPackage(ResearchPackageAdapter):
    def initialize(self, config):
        ...
    def compile_potential(self, source_path):
        ...
    def run_workflow(self, input_script):
        ...
```

When local package sources from the Shah Research Group become available, they can be plugged directly into this adapter without altering the core chatbot.

---

## 8. Security & Sandbox Controls

- **No Arbitrary Shell Calls**: Forbidden commands (`rm`, `del`, `sudo`, `shell`, `system`, `curl`, `wget`) are strictly blocked by the execution runner.
- **Confirmation Gate**: Generated code is never executed without explicit user confirmation in the UI.
- **Process Isolation**: Every simulation run takes place in an isolated workspace with a 180-second timeout guard.
- **Zero Cloud Leakage**: No network traffic or remote telemetry is dispatched.
