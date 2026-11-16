"""Synthetic-only contracts and exact equivalence to the archived FULL arm."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from cellmem_full_axis import predict, FROZEN_CORE_SHA256
from cellmem_full_axis import _frozen_core as core
from cellmem_full_axis.io import load_inputs

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("demo", ROOT / "examples/make_synthetic_inputs.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class FrozenMethodContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.folder = demo.create(self.base / "inputs")
        self.ref, self.bulk, _ = load_inputs(self.folder / "reference.npz", self.folder / "bulk.npz")

    def tearDown(self):
        self.tmp.cleanup()

    def test_core_bytes(self):
        self.assertEqual(hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest(), FROZEN_CORE_SHA256)
        archived = ROOT / "frozen/FULL_DONOR_PRECISION_20261116/core.py"
        self.assertEqual(archived.read_bytes(), Path(core.__file__).read_bytes())

    def test_full_path_exactly_matches_archived_forward(self):
        r, b = self.ref, self.bulk
        actual = predict(r["F"], r["reference_count_sums"], b["Y"], r["column_type"], n_types=len(r["types"]))
        expected, _ = core.forward(r["F"], r["reference_count_sums"], np.array([0, 1, 2]),
                                   b["Y"], r["column_type"], len(r["types"]))
        expected = expected["FULL_DONOR_PRECISION"]
        np.testing.assert_array_equal(actual["prediction"], expected["prediction"])
        np.testing.assert_array_equal(actual["coefficients"], expected["coefficients"])
        self.assertEqual(actual["diagnostics"], expected["diagnostics"])
        self.assertTrue(all(x["numeric_certified"] for x in actual["diagnostics"]))
        self.assertEqual(actual["reference_background"]["variance_unsupported_types"], [2])

    def test_weighted_poisson_zero_row_keeps_linear_term(self):
        models, _ = core.prepare(self.ref["F"], self.ref["reference_count_sums"], np.array([0, 1]))
        P = models["FULL_COUNT"]
        q = np.array([.3, .7, 0., 0., 0.])
        w = np.array([.9, .2, .4, .8, .5])
        x, d = core.solve(P, q, w)
        expected = float(np.sum(w * ((P @ x) - q * np.log(P @ x))))
        self.assertAlmostEqual(d["objective"], expected, places=14)
        gradient = w @ P - P.T @ (q * w / (P @ x))
        self.assertLessEqual(float(gradient @ x - gradient.min()), core.GAP_TOL)

    def test_gene_permutation_rejected(self):
        np.savez(self.base / "wrong_genes.npz", Y=self.bulk["Y"], genes=self.bulk["genes"][::-1], ids=self.bulk["ids"])
        with self.assertRaisesRegex(ValueError, "exactly aligned"):
            load_inputs(self.folder / "reference.npz", self.base / "wrong_genes.npz")

    def test_truth_fields_rejected(self):
        np.savez(self.base / "with_truth.npz", **self.bulk, truth=np.ones((2, 3)))
        with self.assertRaisesRegex(ValueError, "Forbidden target information"):
            load_inputs(self.folder / "reference.npz", self.base / "with_truth.npz")

    def test_duplicate_donor_type_rejected(self):
        r = dict(self.ref)
        r["donor_labels"] = np.array(["REF1"] * 5)
        np.savez(self.base / "duplicate_reference.npz", **r)
        with self.assertRaisesRegex(ValueError, "Duplicate donor/type"):
            load_inputs(self.base / "duplicate_reference.npz", self.folder / "bulk.npz")

    def test_unrepresented_output_type_rejected(self):
        r, b = self.ref, self.bulk
        with self.assertRaisesRegex(ValueError, "Every output type"):
            predict(r["F"], r["reference_count_sums"], b["Y"], r["column_type"], n_types=4)

    def test_cli_writes_prediction_lock_and_refuses_overwrite(self):
        out = self.base / "prediction_run"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        cmd = [sys.executable, "-m", "cellmem_full_axis", "--reference", str(self.folder / "reference.npz"),
               "--bulk", str(self.folder / "bulk.npz"), "--out", str(out)]
        p = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        lock = json.loads((out / "PREDICTION_LOCK.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["samples"], 2)
        self.assertFalse(lock["scoring_performed"])
        for name, h in lock["outputs"].items():
            self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), h)
        with np.load(out / "predictions.npz", allow_pickle=False) as z:
            self.assertIn("initial_coefficients", z.files)
            self.assertIn("precision", z.files)
        q = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertNotEqual(q.returncode, 0)
        self.assertIn("must not exist", q.stderr)


if __name__ == "__main__":
    unittest.main()
