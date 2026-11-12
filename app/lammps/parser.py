"""Deterministic Thermodynamic and Simulation Output Parser with Time-Series Extraction."""
from pathlib import Path
from typing import Dict, List, Any
import math

def _round(x: float) -> float:
    """4 decimals, like before, but at least 4 significant figures for small values.

    Plain round(x, 4) turned a water self-diffusion coefficient in real units
    (v_D_fit ~ 2.3e-05 A^2/fs) into 0.0, and small pressures or MSD slopes likewise.
    """
    if x == 0 or not math.isfinite(x):
        return x
    return round(x, max(4, 3 - math.floor(math.log10(abs(x)))))


def _json_number(x: float):
    """x, or None for nan/inf, which JSON can't carry (the browser's JSON.parse rejects NaN)."""
    return x if math.isfinite(x) else None


class ThermoParser:
    """Parses LAMMPS log files, computes statistics, and extracts time-series for visualization."""

    def parse_log(self, log_path: str) -> Dict[str, Any]:
        p = Path(log_path)
        if not p.exists():
            return {"parsed": False, "error": f"Log file does not exist: {log_path}"}

        content = p.read_text(encoding="utf-8", errors="replace")
        return self.parse_log_text(content)

    def parse_log_text(self, log_text: str) -> Dict[str, Any]:
        """Parses thermodynamic tables directly from raw string content."""
        lines = log_text.splitlines()

        thermo_blocks = []
        in_thermo = False
        headers: List[str] = []
        current_rows: List[List[float]] = []
        warnings_found = []
        errors_found = []

        for line in lines:
            line_str = line.strip()

            if line_str.startswith("WARNING:"):
                warnings_found.append(line_str)
            elif line_str.startswith("ERROR:"):
                errors_found.append(line_str)

            # Detect start of thermo table
            if "Step" in line_str and any(col in line_str for col in ["Temp", "TotEng", "E_total", "PotEng", "Press", "E_pair", "Pzz"]):
                in_thermo = True
                headers = line_str.split()
                current_rows = []
                continue

            if in_thermo:
                # LAMMPS prints warnings in the middle of a run (e.g. lost atoms, neighbor list
                # rebuilds); the table carries on after them, so only note them.
                if line_str.startswith("WARNING:"):
                    continue
                if "Loop time of" in line_str or "ERROR" in line_str or line_str.startswith("---"):
                    in_thermo = False
                    if headers and current_rows:
                        thermo_blocks.append({"headers": headers, "rows": current_rows})
                    continue

                tokens = line_str.split()
                try:
                    vals = [float(t) for t in tokens]
                    if len(vals) == len(headers):
                        current_rows.append(vals)
                except ValueError:
                    in_thermo = False
                    if headers and current_rows:
                        thermo_blocks.append({"headers": headers, "rows": current_rows})

        if in_thermo and headers and current_rows:
            thermo_blocks.append({"headers": headers, "rows": current_rows})

        if not thermo_blocks:
            return {
                "parsed": True,
                "blocks": [],
                "warnings": warnings_found,
                "errors": errors_found,
                "summary": {},
                "time_series": {},
                "stability": "Inconclusive (no thermo rows)",
                "message": "No thermodynamic data tables found in log."
            }

        all_stage_summaries = [self._compute_summary(b["headers"], b["rows"]) for b in thermo_blocks]
        latest = thermo_blocks[-1]
        summary = all_stage_summaries[-1]
        stability = self._check_stability(latest["headers"], latest["rows"])
        time_series = self._extract_time_series(latest["headers"], latest["rows"])

        # A run that blows up prints nan/inf. Those rows used to be averaged in (NaN means),
        # sent to the browser as bare NaN (not valid JSON), and a short blown-up run was even
        # reported as "Equilibrated".
        bad_rows = sum(1 for r in latest["rows"] if not all(math.isfinite(v) for v in r))
        if bad_rows:
            stability["non_finite_rows"] = bad_rows
            stability["temperature_stabilized"] = False
            verdict = f"Unstable ({bad_rows} thermo row(s) with nan/inf: the run blew up)"
        else:
            verdict = "Equilibrated" if stability.get("temperature_stabilized", True) else "Fluctuating"

        return {
            "parsed": True,
            "stage_count": len(thermo_blocks),
            "all_stages": all_stage_summaries,
            "headers": latest["headers"],
            "row_count": len(latest["rows"]),
            "summary": summary,
            "stability": verdict,
            "stability_analysis": stability,
            "time_series": time_series,
            "warnings": warnings_found,
            "errors": errors_found,
            "raw_rows": [[_json_number(v) for v in r] for r in latest["rows"]]
        }

    def _extract_time_series(self, headers: List[str], rows: List[List[float]]) -> Dict[str, List[float]]:
        series = {}
        for idx, col in enumerate(headers):
            series[col] = [_json_number(r[idx]) for r in rows]   # nan/inf -> None (a gap)
        return series

    def _compute_summary(self, headers: List[str], rows: List[List[float]]) -> Dict[str, Any]:
        if not rows:
            return {}
        summary = {}
        for idx, col in enumerate(headers):
            values = [r[idx] for r in rows if math.isfinite(r[idx])]
            skipped = len(rows) - len(values)
            if not values:
                summary[col] = {"non_finite": skipped}
                continue
            n = len(values)
            mean_val = sum(values) / n
            variance = sum((x - mean_val) ** 2 for x in values) / n
            std_dev = math.sqrt(variance)
            drift = values[-1] - values[0]

            summary[col] = {
                "initial": _round(values[0]),
                "final": _round(values[-1]),
                "min": _round(min(values)),
                "max": _round(max(values)),
                "mean": _round(mean_val),
                "std_dev": _round(std_dev),
                "drift": _round(drift)
            }
            if skipped:
                summary[col]["non_finite"] = skipped   # stats above use the finite values only
        return summary

    def _check_stability(self, headers: List[str], rows: List[List[float]]) -> Dict[str, Any]:
        if len(rows) < 8:
            return {"stabilized": "Inconclusive (short run)", "temperature_stabilized": True}

        res = {}
        cutoff = int(len(rows) * 0.75)
        recent_rows = rows[cutoff:]

        if "Temp" in headers:
            t_idx = headers.index("Temp")
            recent_temps = [r[t_idx] for r in recent_rows if math.isfinite(r[t_idx])]
            if not recent_temps:
                res["temperature_stabilized"] = False
                return res
            recent_mean = sum(recent_temps) / len(recent_temps)
            recent_std = math.sqrt(sum((x - recent_mean) ** 2 for x in recent_temps) / len(recent_temps))
            fluctuation_pct = (recent_std / max(abs(recent_mean), 1e-4)) * 100
            res["temperature_stabilized"] = fluctuation_pct < 15.0
            res["temperature_fluctuation_pct"] = round(fluctuation_pct, 2)
            res["recent_mean_temp"] = round(recent_mean, 2)

        return res
