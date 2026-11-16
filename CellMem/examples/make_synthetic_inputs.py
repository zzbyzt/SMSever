"""Create tiny public synthetic capsules. No research or patient data is read."""
import argparse
from pathlib import Path
import numpy as np


def create(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    F = np.array([[.70, .64, .04, .06, .03], [.05, .07, .64, .70, .02],
                  [.10, .12, .07, .05, .70], [.15, .17, .25, .19, .25],
                  [0., 0., 0., 0., 0.]])
    genes = np.array(["DEMO_G1", "DEMO_G2", "DEMO_G3", "DEMO_G4", "DEMO_G5"])
    types = np.array(["DEMO_A", "DEMO_B", "DEMO_C"])
    count_sums = F * np.array([10000., 9000., 11000., 10000., 12000.])
    weights = np.array([[.4, .1, .2, .2, .1], [0., 0., .3, .2, .5]]).T
    Y = np.round((F @ weights) * np.array([10000., 15000.]))
    Y[4] = [2., 0.]
    np.savez_compressed(folder / "reference.npz", F=F, reference_count_sums=count_sums,
                        column_type=np.array([0, 0, 1, 1, 2]), genes=genes, types=types,
                        donor_labels=np.array(["REF1", "REF2", "REF1", "REF2", "REF1"]))
    np.savez_compressed(folder / "bulk.npz", Y=Y, genes=genes, ids=np.array(["DEMO_001", "DEMO_002"]))
    return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    print(create(parser.parse_args().out))
