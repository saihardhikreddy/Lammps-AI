# Local LAMMPS Liquid Research Assistant

> Local-first assistant for liquid-state molecular dynamics with LAMMPS: validated script generation, local execution with live streaming, and transport-property analysis.

---

## 1. Project Overview & Scope

The assistant focuses on **liquid-state statistical mechanics and transport properties**. Solid mechanics (tensile deformation, stress-strain curves) is out of scope and is refused explicitly.

**What runs where**

| Layer | Dependencies | Network |
|---|---|---|
| Script generation, validation, local LAMMPS execution, log/trajectory parsing, web UI server | Python 3.9+ standard library only | none |
| Optional Google Gemini answers for documentation and general questions | `google-genai`, a `GEMINI_API_KEY` | sends the question and retrieved context to Google's API |
| Optional local LLM (Ollama) | a running `ollama serve` | localhost only |
| Optional OVITO post-run rendering | `ovito` (see `requirements-visualization.txt`) | none; needs a display/GPU |
| Web UI styling | Tailwind CSS loaded from its CDN | the page layout needs internet access; the app still works without it, unstyled |

Script requests for supported liquids **always** use the deterministic, validated templates, never an LLM. An LLM is only used for questions and for systems the templates do not cover, and any script it writes is labelled **"Unverified script"** in the answer.

### Core Capabilities

1. **Liquid script generation** (all verified to run in LAMMPS 22 Jul 2025):
   - **Lennard-Jones fluid / liquid argon** (`units lj`; argon temperatures in K are mapped to T* = T / 119.8 K)
   - **Rigid SPC/E water** (`units real`): real three-site molecules built from a molecule template with charges −0.8476 e / +0.4238 e, bonds and angle, held rigid by SHAKE, PPPM long-range electrostatics. The configurational energy (≈ −11.3 kcal/mol per molecule) and D (≈ 2.3×10⁻⁵ cm²/s) match published SPC/E values.
   - **Molten metals** (Al, Cu, Ni, Fe; EAM potentials): the starting crystal is superheated at zero pressure to max(1.5 T_m, T + 300 K) so it actually melts, then cooled to the target temperature and equilibrated before production.
2. **Parameter honesty**: every stated parameter (ensemble, temperature, timestep with fs/ps units, atom count, dump and thermo intervals) is used in the script or reported as overridden, with the reason. The simulation plan always matches the script.
3. **Transport-aware ensembles**: diffusion and viscosity runs default to **NVE production** after NVT equilibration, because a thermostat perturbs the dynamics being measured. An explicitly requested NVT/NPT/Langevin production is honored and flagged as biased.
4. **Transport properties computed by LAMMPS itself**:
   - **Self-diffusion** D = slope(MSD)/6, fitted in-run and printed as `v_D_fit`
   - **Shear viscosity** by Green-Kubo (after LAMMPS `examples/VISCOSITY`): stress autocorrelation over 5 τ (LJ), 2 ps (water) or 1 ps (metals), integrated in-run and printed as `v_eta` (mPa·s for water/metals). A single run gives a rough estimate; converge with longer runs and several seeds.
   - **Structure**: time-averaged g(r)
   - `app/lammps/diffusion.py` and `app/lammps/viscosity.py` provide the same analyses for post-processing output files.
5. **Phase sanity checks**: warnings when the requested temperature is below the melting/triple point, with the temperature actually simulated stated explicitly.
6. **Static validation**: units, box/atoms, force field, integrators, velocity and timestep checks, plus: long-range solver with no charges, SHAKE with no bonds, transport measured under a thermostat, and file paths that leave the run folder.
7. **Live execution streaming**: Server-Sent Events stream LAMMPS stdout and complete trajectory frames while the run is in progress; a configurable timeout (`LAMMPS_EXECUTION_TIMEOUT`, default 900 s) kills the whole process tree.
8. **WebGL2 trajectory player** (`trajectory-viewer.js`): instanced rendering, play/pause/scrub, orbit/pan/zoom, coloring by element or per-atom kinetic energy.
9. **Synthetic-data labelling**: without a LAMMPS binary, a built-in engine produces an illustrative trajectory so the viewer can be demonstrated. Its log file starts with `# SYNTHETIC DATA … NOT by LAMMPS`, and the UI shows a persistent banner. These numbers are not simulation results.
10. **Optional OVITO rendering**: final-frame image and coordination histogram when `ovito` is installed and a display is available; skipped gracefully otherwise.
11. **Error diagnostics** for common LAMMPS failures (lost atoms, PPPM out-of-range, illegal fix/pair_style, missing files, NaN coordinates).
12. **Pluggable Shah adapter** (`app/adapters/shah_adapter.py`) wrapping the diffusion module.

### Intentional design boundaries
- No tensile/deformation or other solid-mechanics workflows.
- No quench/cooling-rate protocols yet (such requests are answered with a liquid equilibration at the final temperature, and the answer says so).
- The viewer does not draw bonds, clipping planes, or color by computed properties other than kinetic energy.

---

## 2. Layered Architecture

```text
┌────────────────────────────────────────────────────────┐
│                   Web Chatbot UI                       │
│    (Vanilla JS + HTML5 + CSS3 + Confirmation Modal)    │
└───────────────────────────▲────────────────────────────┘
                            │ REST + SSE (/api/chat, /api/run, /api/run/stream, /api/preset)
                            │ Host + Origin checked, per-session token on every POST
┌───────────────────────────▼────────────────────────────┐
│                    Chatbot Router                      │
│   templates first for supported liquids; LLM optional  │
└─────────┬──────────────┬──────────────┬────────────────┘
          │              │              │
┌─────────▼────────┐ ┌───▼───────────┐ ┌▼────────────────┐
│  Knowledge Base  │ │ Liquid Script │ │ Error Diagnostic│
│  & Retriever     │ │ Generator +   │ │   & Validation  │
│                  │ │ Planner       │ │     Engine      │
└─────────┬────────┘ └───┬───────────┘ └┬────────────────┘
          │              │              │
┌─────────▼──────────────▼──────────────▼────────────────┐
│                 Liquid Transport Core                  │
│   diffusion.py (Einstein MSD) · viscosity.py (GK)      │
│   parser.py (thermo) · trajectory_parser.py (dumps)    │
└───────────────────────────▲────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                 Local LAMMPS Engine                    │
│  detection (version + packages), sandboxed runner,     │
│  timeout watchdog, synthetic fallback (labelled)       │
└────────────────────────────────────────────────────────┘
```

---

## 3. Requirements

- **Python** 3.9+ (standard library only for the core).
- **LAMMPS** (optional for execution): `lmp`, `lmp_serial`, `lmp_mpi`, a WSL2 Ubuntu install, or a path in `LAMMPS_EXECUTABLE`. SPC/E water needs the **MOLECULE**, **RIGID** and **KSPACE** packages; without KSPACE the generator falls back to truncated Coulomb and says so. Metal potentials are found via `LAMMPS_POTENTIALS` or the standard install locations.
- **Optional**: `pip install -r requirements.txt` (Gemini + .env support), `pip install -r requirements-visualization.txt` (OVITO).

Configuration lives in `.env` (see `.env.example`). `.env` is git- and Vercel-ignored; never commit it.

---

## 4. Quick Start

### Linux / macOS / WSL

```bash
./run.sh check   # LAMMPS binary and package detection
./run.sh test    # full test suite
./run.sh         # start the web server
```

Or directly:

```bash
python3 scripts/check_lammps.py
python3 -m unittest discover -s tests -p "test_*.py" -v
python3 run.py
```

### Windows (PowerShell)

```powershell
python scripts\check_lammps.py
python -m unittest discover -s tests -p "test_*.py" -v
python run.py
```

Then open `http://127.0.0.1:8000`.

When LAMMPS is installed, `tests/test_review_regressions.py` also runs every template in it and checks the physics (SPC/E energy and density, aluminium actually melting, Green-Kubo output); those tests are skipped otherwise.

---

## 5. Usage Examples

**A. SPC/E water** — *"Generate a liquid water simulation at 300 K using NVT ensemble"*
216 rigid SPC/E molecules at 1.0 g/cm³: minimization → SHAKE → NVT equilibration (5 ps) → NVT production.

**B. Self-diffusion** — *"Calculate the diffusion coefficient of liquid argon at 85 K"*
LJ fluid at T* = 0.71: NVT equilibration → **NVE** production with `compute msd`; LAMMPS prints D (σ²/τ) as `v_D_fit`. (Measured: D* ≈ 0.034 ≈ 1.9×10⁻⁵ cm²/s.)

**C. Shear viscosity** — *"Calculate shear viscosity using Green-Kubo for Lennard-Jones liquid"*
NVE production with `fix ave/correlate` on pxy, pxz, pyz; the Green-Kubo integral is evaluated in-run and printed as `v_eta`.

**D. Molten metal** — *"Simulate molten copper at 1450 K"*
Superheat melt of the fcc crystal at 0 bar, cool to 1450 K, NPT equilibration, then production. Requests below T_m are simulated just above T_m, and the answer states the temperature used.

**E. Out of scope** — *"Simulate tensile deformation of copper"*
Explains that solid mechanics is not supported and lists the supported liquid workflows.

---

## 6. Security Controls

The server binds to `127.0.0.1` by default and is meant for local, single-user use.

- **Host and Origin checks**: requests whose `Host` or `Origin` is not this server are rejected (blocks cross-site requests and DNS rebinding). CORS headers are only sent back to the server's own origin.
- **Session token**: a random token is minted at startup and injected into `index.html`; every POST (chat, run, API-key, workspace, preset) and the SSE stream require it.
- **Run IDs**: validated against `^[A-Za-z0-9_-]{1,64}$` and confirmed to resolve inside `simulations/` (checked in both the server and the runner).
- **Script sandbox**: `shell`, `python`, `system` and `quit` are blocked, and any file path that is absolute or contains `..` (e.g. in `print … file`, `dump`, `write_data`) is rejected, so scripts can only write inside their run folder.
- **Human confirmation**: the UI shows the script and validation result before running; the Run button is disabled when validation fails.
- **Timeout**: runs are killed, together with any child processes, after `LAMMPS_EXECUTION_TIMEOUT` seconds.
- **Cloud use is opt-in**: nothing leaves the machine unless a Gemini API key is configured, and then only questions routed to Gemini (never script generation for supported liquids).
