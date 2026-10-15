# Changes — 30 Sep 2026 review fixes

All generated scripts were run in LAMMPS (22 Jul 2025, Update 4). Test suite: 135 tests
(`tests/test_review_regressions.py` is new; its real-LAMMPS checks are skipped when no binary is installed).

## Scientific correctness
- **SPC/E water is now water.** Before: `create_atoms 1 box` made a box of uncharged oxygen atoms (no H, no bonds), so SHAKE and PPPM had nothing to act on. Now: 216 molecules built from a molecule template (charges, bonds, angle), minimized, then SHAKE-constrained. Measured: PE ≈ −11.3 kcal/mol per molecule, density 1.00 g/cm³, D ≈ 2.3×10⁻⁵ cm²/s (all consistent with published SPC/E).
- **Transport runs default to NVE production.** Before: diffusion/viscosity scripts used `fix nvt` while the plan said NVE. Now NVE unless the user explicitly asks otherwise (then honored and flagged). The plan text follows the script.
- **Metals actually melt.** Before: a 1 ps ramp to T_m + 100 K under NVT left aluminium a crystal (MSD plateau 0.40 Å² at 71,000 bar). Now: zero-pressure superheat to max(1.5 T_m, T + 300 K), hold, cool, equilibrate. Measured: MSD keeps growing and volume rises by 16%.
- **Nickel** uses `pair_style eam` for the funcfl file `Ni_u3.eam` (was `eam/alloy`, which fails).
- **Green-Kubo**: correlation window raised from 50 steps to 5 τ / 2 ps / 1 ps, and the viscosity is integrated in-run (`v_eta`, mPa·s for real/metal units). Diffusion D is fitted in-run (`v_D_fit`).
- **LJ NPT** runs at the equilibrated NVT pressure (P* = 0 would boil a T* = 1.44 fluid).
- Langevin production supported for all systems (water/metal previously fell back to NVE silently).
- Stated **timestep units** (fs/ps) are converted; **atom count, dump and thermo intervals** are now used; quench requests say the protocol isn't implemented instead of silently substituting.
- **KSPACE fallback**: Ewald is part of KSPACE, so without KSPACE the script now uses truncated Coulomb with an explicit warning. Package detection parses `lmp -help` correctly (it previously found no packages).
- Solid-mechanics von Mises stress removed from the liquid templates; the synthetic engine no longer fabricates a stress field.
- "Calculate the diffusion coefficient of …" style requests now generate scripts (previously they fell through to a documentation snippet).

## Honesty / integrity
- Script requests for supported liquids always use the validated templates, never an LLM. LLM-written scripts (unsupported systems only) are labelled "Unverified script".
- The synthetic engine's log starts with `# SYNTHETIC DATA … NOT by LAMMPS` instead of a fake `LAMMPS (2 Aug 2023)` header and fake performance lines.
- README claims corrected (optional cloud Gemini, CDN dependency, real capabilities). pydantic removed; the core is standard-library only again. `requirements.txt` lists the optional packages.

## Security & runtime
- **Public Vercel deployment**: workspace endpoints disabled (they allowed reading any file, including a deployed `.env`). `.env`, `data/memory.db` and zips are now git- and Vercel-ignored. Workspace reads refuse dotfiles, keys and databases.
- Local server: no wildcard CORS; Host and Origin checks (DNS rebinding); session token required on every POST; JSON 400/500 errors instead of dropped connections; `/api/key/set` merges into `.env` instead of overwriting it (and tests no longer overwrite the real `.env`).
- Scripts can no longer write files outside their run folder (`print … file /abs/path`, `../`).
- The run timeout actually fires (watchdog kills the whole process tree; previously `readline()` blocked forever). Timeout configurable via `LAMMPS_EXECUTION_TIMEOUT` (default 900 s). Old runs are evicted from memory.
- `/api/status` uses cached LAMMPS detection (`?refresh=1` to force).
- `.env` is loaded before settings are read (HOST/PORT in `.env` previously had no effect); a stdlib parser is used when python-dotenv is missing.
- UI: viewer presets come from the server's generator; the synthetic banner resets per run and stays hidden offline; duplicate `trajectory-viewer.js` include removed.
