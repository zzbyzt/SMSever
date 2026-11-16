# Frozen full-axis donor-precision candidate

This source snapshot preserves `FULL_DONOR_PRECISION`, originally frozen from the 2026-11-15 R1 development experiment. Subsequent evaluations are separate from this code-only publication. It is a development candidate, not a replacement of frozen VarPool and not a claim of superiority across all endpoints or datasets. The later R2 reference gates returned this same base path; failed calibration and state candidates are not silently enabled here.

## Method and statistical meaning

The reference has one column for each observed donor/type combination. `F` contains normalized complete-axis RNA profiles, `reference_count_sums` their raw summed counts, and `column_type` maps reference columns to known output types. All bulk samples must share the exact ordered gene axis. There is no target-truth input, automatic annotation, gene intersection, zero filling, neural training, or threshold selection.

1. Let `d` be the median reference column raw count total and `G` the gene count. Use the frozen uniform prior `epsilon=1/(d+1)` and `P=(1-epsilon)*F+epsilon/G`. This makes every reference column strictly positive; it is a model assumption, not imputation of observed counts or an UNKNOWN component.
2. Solve the unweighted complete-axis count objective on nonnegative reference-column weights summing to one. Sum weights by type to obtain the initial composition `pi0`.
3. For each type with `D>=2` donor profiles, estimate `C=mean(P)` and `V=sample_variance(P)/D`. Compute `mu=C*pi0`, `v=V*(pi0**2)`, and once-only precision `w=mu/(mu+N*v)` using observed bulk depth `N`. Refit with the same reference matrix and fixed `w`, then sum coefficients by type.

The fixed-weight objective is `sum_g w_g [(P*x)_g - q_g*log((P*x)_g)]`, where `q=Y/N`. The linear term must remain: when weighted, it is generally not constant. Zero-count target genes still penalize assigned expression mass. The solver is the exact archived SLSQP, equality-constrained Newton refinement and coordinate-polishing implementation, with simplex first-order gap at most `1e-8` and feasibility at most `1e-10`. Certification concerns each fixed convex subproblem, not joint global optimality of the whole two-step procedure.

The estimator uses variance of a reference mean, not predictive variance for a new donor. A single-donor type has an unsupported variance estimate: `V` remains numerically zero and is explicitly reported. No VarPool borrowing is performed. The output is a closed vector of known-type RNA fractions on the supplied complete input axis. It is not a cell fraction, presence probability, calibrated interval, or UNKNOWN identity. Genes outside a historical identity panel participate in FULL inference; the 828 index is not a parameter of this default path.

## Portable input contract

Reference NPZ required arrays:

| Array | Shape | Meaning |
|---|---|---|
| `F` | G × J | Finite nonnegative normalized donor/type RNA spectra |
| `reference_count_sums` | G × J | Raw reference count sums; positive column totals |
| `column_type` | J | Contiguous integer IDs 0…K−1; every output type represented |
| `types` | K | Unique type-name strings |
| `genes` | G | Unique gene strings in the actual measured order |
| `donor_labels` | J, optional | Donor IDs; duplicate donor/type pairs are rejected when supplied |

Bulk NPZ requires `Y` (G × samples nonnegative counts), `genes` (same order), and `ids` (unique anonymous sample strings). The frozen historical anonymous capsule also embeds reference metadata; that registered metadata is ignored and recorded. No generic unknown fields, pickled objects, truth keys, or target-donor keys are allowed. The CLI refuses scoring and sealed/test directories, requires a new output directory, and performs no automatic path discovery. These are application checks, not an operating-system sandbox. Users remain responsible for verifying upstream split and label provenance; absence of a `truth` field does not prove that the data or development history is leak-free.

Positive counts must be on the same untransformed measurement axis; no implicit log/TPM conversion is done. Research capsules are distributed separately from this code-only publication. Missing measured genes are a data-admission issue, not repaired by this package.

## Run and audit

With the project installed, or `src` on `PYTHONPATH`:

```powershell
python examples/make_synthetic_inputs.py --out demo_inputs
python -m cellmem_full_axis --reference demo_inputs/reference.npz --bulk demo_inputs/bulk.npz --out demo_prediction
python -m unittest discover -s tests -p "test_frozen_method.py" -v
```

For an uninstalled checkout on PowerShell, set `$env:PYTHONPATH = (Resolve-Path ./src).Path` first. On POSIX use `PYTHONPATH=src python -m cellmem_full_axis ...`. The reference environment used Python 3.11.5, NumPy 1.26.2 and SciPy 1.11.4 on Windows; the synthetic contract tests here use those same local versions. Other platforms or package versions are unverified. Plotting and R are not runtime dependencies of this default predictor.

`RUN_LOCK.json` records code, core and input hashes before inference. `predictions.npz` stores type fractions, final and initial reference-column coefficients, full precision vectors, reference means/variances and support counts. `NUMERICS.json` retains convergence and unsupported-variance information. `PREDICTION_LOCK.json` binds final output hashes. `predictions.tsv` keeps every sample/type row with certification status. An uncertified finite fit is saved and returns exit code 2, never replaced by a fabricated zero. Runtime exceptions produce `RUN_FAILURE.json`; outputs are never overwritten.

The public example is synthetic, not a research mixture or patient record. Testing verifies exact equality of this FULL-only wrapper to the archived FULL branch, preserved weighted-Poisson behavior including zero-count rows, axis and truth-field guards, unsupported variance reporting, and prediction locks. No historical experiment is rerun during packaging.
