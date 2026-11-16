"""Portable prediction CLI with explicit input/output hashes, not a scorer."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import numpy as np
from . import METHOD_ID, FROZEN_CORE_SHA256, __version__
from .api import predict
from .io import load_inputs, _path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description="Frozen FULL_DONOR_PRECISION RNA-fraction prediction. No target truth input.")
    p.add_argument("--reference", required=True, type=Path)
    p.add_argument("--bulk", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path, help="New output directory; existing directories are refused")
    a = p.parse_args(argv)
    out = a.out.resolve()
    if out.exists():
        p.error("--out must not exist; locked outputs are never overwritten")
    try:
        reference_path, bulk_path = _path(a.reference), _path(a.bulk)
        input_hashes = {"reference": sha(reference_path), "bulk": sha(bulk_path)}
        ref, bulk, checks = load_inputs(reference_path, bulk_path)
        if input_hashes != {"reference": sha(reference_path), "bulk": sha(bulk_path)}:
            raise ValueError("Input files changed while being loaded")
    except (ValueError, OSError, KeyError) as e:
        p.error(str(e))
    code = Path(__file__).parent
    if sha(code / "_frozen_core.py") != FROZEN_CORE_SHA256:
        p.error("Frozen numerical core hash mismatch")
    out.mkdir(parents=True)
    dump(out / "RUN_LOCK.json", {
        "status": "LOCKED_BEFORE_PREDICTION", "created_utc": datetime.now(timezone.utc).isoformat(),
        "method": METHOD_ID, "package_version": __version__, "frozen_core_sha256": FROZEN_CORE_SHA256,
        "code_sha256": {f.name: sha(f) for f in sorted(code.glob("*.py"))},
        "input_sha256": input_hashes, "input_file_names": {"reference": a.reference.name, "bulk": a.bulk.name},
        "input_checks": checks,
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "numpy": importlib.metadata.version("numpy"), "scipy": importlib.metadata.version("scipy")},
        "quantity": "RNA_fraction_on_supplied_complete_input_gene_axis",
        "output_types": [str(x) for x in ref["types"]], "target_truth_read": False,
        "success_criteria": "unchanged_frozen_numerical_certificate_only_not_scientific_acceptance",
    })
    try:
        result = predict(ref["F"], ref["reference_count_sums"], bulk["Y"],
                         ref["column_type"], n_types=len(ref["types"]))
        if input_hashes != {"reference": sha(a.reference), "bulk": sha(a.bulk)}:
            raise RuntimeError("Input files changed while prediction was running")
        arrays = {k: v for k, v in result.items() if isinstance(v, np.ndarray)}
        np.savez_compressed(out / "predictions.npz", **arrays,
                            genes=ref["genes"], ids=bulk["ids"], types=ref["types"])
        dump(out / "NUMERICS.json", {"final": result["diagnostics"], "initial": result["initial_diagnostics"],
                                      "reference_background": result["reference_background"]})
        with (out / "predictions.tsv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["sample_id", "type_id", "RNA_fraction", "numeric_certified", "status"])
            for sid, vec, d in zip(bulk["ids"], result["prediction"], result["diagnostics"]):
                for typ, val in zip(ref["types"], vec):
                    w.writerow([sid, typ, repr(float(val)), d["numeric_certified"],
                                "CERTIFIED" if d["numeric_certified"] else "FINITE_UNCERTIFIED"])
        passed = sum(bool(d["numeric_certified"]) for d in result["diagnostics"])
        dump(out / "PREDICTION_LOCK.json", {
            "status": "COMPLETE" if passed == len(bulk["ids"]) else "COMPLETE_WITH_UNCERTIFIED_OUTPUTS",
            "method": METHOD_ID, "samples": len(bulk["ids"]), "numeric_certified": passed,
            "run_lock_sha256": sha(out / "RUN_LOCK.json"),
            "outputs": {name: sha(out / name) for name in ["predictions.npz", "predictions.tsv", "NUMERICS.json"]},
            "scoring_performed": False, "target_truth_read": False,
        })
    except Exception as e:
        dump(out / "RUN_FAILURE.json", {"status": "FAILED", "exception_type": type(e).__name__, "message": str(e)})
        raise
    print(json.dumps({"output": str(out), "samples": len(bulk["ids"]), "certified": passed}))
    return 0 if passed == len(bulk["ids"]) else 2


if __name__ == "__main__":
    sys.exit(main())
