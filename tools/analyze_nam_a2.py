"""Measure relative small-signal EQ curves from A2 NAM captures.

The NAM public Python package normally imports training-only dependencies on
startup.  This analysis only needs its inference model, so it supplies the one
training helper imported by the base class and loads the model package directly.
No pedal files are read or modified.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import numpy as np
import torch


def _load_nam_runtime():
    """Load NAM inference without importing its GUI/trainer dependency tree."""
    site = next(Path(p) for p in sys.path if (Path(p) / "nam").is_dir())
    package = types.ModuleType("nam")
    package.__path__ = [str(site / "nam")]
    sys.modules.setdefault("nam", package)
    data = types.ModuleType("nam.data")
    data.wav_to_tensor = lambda _: None  # only used by training metadata helpers
    sys.modules.setdefault("nam.data", data)
    from nam.models._from_nam import init_from_nam
    return init_from_nam


FREQUENCIES = np.array([40.0, 80.0, 150.0, 300.0, 700.0, 1000.0, 3500.0, 8000.0])
FS = 48_000
SECONDS = 1.0
SETTLE_SAMPLES = FS // 2
AMPLITUDE = 0.01


def load_full(path: Path):
    init_from_nam = _load_nam_runtime()
    contents = json.loads(path.read_text(encoding="utf-8"))
    if contents.get("architecture") != "SlimmableContainer":
        raise ValueError(f"{path.name}: expected A2 SlimmableContainer")
    full = max(contents["config"]["submodels"], key=lambda item: item["max_value"])
    model = init_from_nam(full["model"])
    model.eval()
    return model, contents


def measure(model: torch.nn.Module) -> np.ndarray:
    """Return output/input RMS gain for the named frequencies at low level."""
    samples = int(FS * SECONDS)
    n = torch.arange(samples, dtype=torch.float32)
    tones = torch.stack(
        [AMPLITUDE * torch.sin(2.0 * np.pi * float(freq) * n / FS) for freq in FREQUENCIES]
    )
    with torch.no_grad():
        output = model(tones, pad_start=True).cpu().numpy()
    tail = output[:, SETTLE_SAMPLES:]
    return np.sqrt(np.mean(tail * tail, axis=1)) / (AMPLITUDE / np.sqrt(2.0))


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "Noble Preamp"
    captures = {path.stem: path for path in sorted(root.glob("*.nam"))}
    gains = {}
    metadata = {}
    for name, path in captures.items():
        model, contents = load_full(path)
        gains[name] = measure(model)
        metadata[name] = contents["metadata"]
        print(f"measured {name} (RF={model.receptive_field})")

    flat = gains["Noble Flat"]
    reference_index = int(np.where(FREQUENCIES == 700.0)[0][0])
    report = {
        "frequencies_hz": FREQUENCIES.tolist(),
        "amplitude": AMPLITUDE,
        "normalization": "Each curve is level-matched to Noble Flat at 700 Hz.",
        "captures": {},
    }
    for name, gain in gains.items():
        raw_relative_db = 20.0 * np.log10(np.maximum(gain, 1e-15) / np.maximum(flat, 1e-15))
        level_matched_db = raw_relative_db - raw_relative_db[reference_index]
        report["captures"][name] = {
            "metadata": metadata[name],
            "absolute_gain_db": (20.0 * np.log10(np.maximum(gain, 1e-15))).round(3).tolist(),
            "vs_flat_level_matched_db": level_matched_db.round(3).tolist(),
        }
        table = ", ".join(
            f"{int(f)}Hz {db:+.2f}dB" for f, db in zip(FREQUENCIES, level_matched_db)
        )
        print(f"{name}: {table}")

    destination = root / "nam-a2-eq-analysis.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {destination}")


if __name__ == "__main__":
    main()
