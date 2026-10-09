# ⚛️ LAMMPS-AI: Deep Learning & Molecular Dynamics Integration

LAMMPS-AI is an open research and development framework bridging classical **LAMMPS (Large-scale Atomic/Molecular Massively Parallel Simulator)** molecular dynamics with state-of-the-art **Machine Learning Interatomic Potentials (MLIPs)** and neural network surrogate models.

---

## 🎯 Project Overview

Molecular Dynamics (MD) provides atomistic resolution but is computationally bottlenecked by ab initio Quantum Mechanics (DFT) or limited by empirical force field inaccuracies. LAMMPS-AI explores:

* **Neural Network Potentials (NNPs)**: Integration with frameworks like DeepMD-kit, NequIP, Allegro, and MACE.
* **Active Learning Trajectory Sampling**: Automated uncertainty estimation to identify configurations requiring DFT single-point calculations.
* **Surrogate Property Modeling**: Predicting mechanical, thermodynamic, and vibrational properties directly from simulation trajectories.
* **Analysis & Informatics**: Automated extraction of Radial Distribution Functions ($g(r)$), Mean Squared Displacement (MSD), and stress-strain deformation responses.

---

## 🏗️ Architecture & Roadmap

```
lammps-ai/
├── potentials/          # Trained ML potential weights & descriptors
├── workflows/           # Automated LAMMPS run generators & parsers
├── models/              # PyTorch/JAX models for surrogate property prediction
├── scripts/             # Trajectory conversion (dump -> ASE / PyG datasets)
└── examples/            # Benchmark cases (metals, oxides, polymers)
```

### Planned Milestones
- [x] Initial repository scaffolding and research documentation.
- [ ] Automated input generation (`in.*` scripts) with parameter templates.
- [ ] Integration pipeline for parsing LAMMPS `.dump` outputs to ASE/NetworkX graphs.
- [ ] Benchmark comparison: EAM vs MLIP for FCC Copper tensile deformation.

---

## 🚀 Getting Started

### Prerequisites
* Python 3.10+
* LAMMPS (compiled with ML / Python interface support)
* PyTorch / PyTorch Geometric

```bash
git clone https://github.com/saihardhikreddy/Lammps-AI.git
cd Lammps-AI
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate
```

---

## 📄 License
This project is open-source under the MIT License.
