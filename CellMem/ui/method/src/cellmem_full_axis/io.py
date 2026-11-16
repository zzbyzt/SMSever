"""NPZ input contract; no label-truth file or scoring interface."""

from pathlib import Path
import numpy as np

REFERENCE_FIELDS = {
    "F", "reference_count_sums", "column_type", "types", "genes", "donor_labels",
    "n_cells", "reference_library_per_cell", "reference_observed",
    "identity_indices", "reference_slot_ids",
}
BULK_FIELDS = {"Y", "genes", "ids", "Y_library_size", "reference_zero_count_mass", "reference_zero_RNA_mass"}


def _strings(a, name):
    a = np.asarray(a)
    if a.ndim != 1 or a.dtype.kind not in "US":
        raise ValueError(f"{name} must be a one-dimensional string array")
    a = a.astype(str)
    if not len(a) or any(not s.strip() or any(c in s for c in '\t\r\n') for s in a):
        raise ValueError(f"{name} contains empty or multiline identifiers")
    return a


def _path(p):
    p = Path(p).resolve(strict=True)
    if any(part.casefold() in {"test", "sealed_test", "sealed", "scoring", "evaluation"} for part in p.parts):
        raise ValueError("Prediction CLI refuses scoring or sealed/test directories")
    if not p.is_file() or p.suffix.lower() != ".npz":
        raise ValueError("Input must be an existing NPZ file")
    return p


def _read(p, allowed, required):
    p = _path(p)
    with np.load(p, allow_pickle=False) as z:
        keys = set(z.files)
        forbidden = [k for k in keys if any(s in k.casefold() for s in ("truth", "target_donor", "target_label"))]
        if forbidden:
            raise ValueError(f"Forbidden target information fields: {sorted(forbidden)}")
        if keys - allowed:
            raise ValueError(f"Unregistered input fields: {sorted(keys-allowed)}")
        if required - keys:
            raise ValueError(f"Missing required input fields: {sorted(required-keys)}")
        return {k: z[k] for k in z.files}


def load_inputs(reference_path, bulk_path):
    """Read reference and anonymous bulk capsules, preserving ordered genes.

    Historical anonymous prediction capsules may duplicate reference metadata;
    those safe, registered fields are ignored and disclosed in the receipt.
    No axes are intersected, no genes are filled, and no labels are inferred.
    """
    ref = _read(reference_path, REFERENCE_FIELDS,
                {"F", "reference_count_sums", "column_type", "types", "genes"})
    bulk = _read(bulk_path, BULK_FIELDS | REFERENCE_FIELDS, {"Y", "genes", "ids"})
    genes, bg = _strings(ref["genes"], "reference genes"), _strings(bulk["genes"], "bulk genes")
    if len(set(genes)) != len(genes) or not np.array_equal(genes, bg):
        raise ValueError("Gene identifiers must be unique and exactly aligned in order; no implicit mapping")
    types, ids = _strings(ref["types"], "types"), _strings(bulk["ids"], "sample ids")
    if len(set(types)) != len(types) or len(set(ids)) != len(ids):
        raise ValueError("Type names and anonymous sample IDs must be unique")
    if ref["F"].ndim != 2 or ref["F"].shape[0] != len(genes):
        raise ValueError("Reference matrix does not match its gene axis")
    if bulk["Y"].ndim != 2 or bulk["Y"].shape != (len(genes), len(ids)):
        raise ValueError("Bulk matrix does not match genes and sample IDs")
    donor_status = "NOT_PROVIDED_ASSUME_DISTINCT_DONOR_TYPE_COLUMNS"
    if "donor_labels" in ref:
        donors = _strings(ref["donor_labels"], "donor_labels")
        c = ref["column_type"]
        if len(donors) != ref["F"].shape[1] or len(c) != len(donors):
            raise ValueError("Donor labels must correspond to reference columns")
        if len(set(zip(donors.tolist(), c.tolist()))) != len(donors):
            raise ValueError("Duplicate donor/type columns would distort the frozen variance estimator")
        donor_status = "DISTINCT_DONOR_TYPE_COLUMNS_VERIFIED"
    return ref, bulk, {
        "donor_provenance_check": donor_status,
        "ignored_reference_metadata_in_bulk": sorted(set(bulk) & (REFERENCE_FIELDS - {"genes"})),
        "gene_mapping": "NONE_EXACT_ORDER_REQUIRED",
        "imputation": "NONE",
        "target_truth_interface": "NONE",
    }
