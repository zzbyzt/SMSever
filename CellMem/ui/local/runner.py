"""Local-only adapter: inspect inputs, then invoke the unchanged frozen CLI."""
from pathlib import Path
import argparse
import gc
import json
import sys
import time

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'method' / 'src'))
import numpy as np
from cellmem_full_axis.io import load_inputs
from cellmem_full_axis.cli import main as frozen_main


def save(path, obj):
    temp = path.with_suffix('.pending')
    temp.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def run(job):
    phase = job / 'phase.json'
    save(phase, {'stage': 'validating', 'updated': time.time()})
    r, b, checks = load_inputs(job / 'reference.npz', job / 'bulk.npz')
    if len(b['ids']) > 200:
        raise ValueError('界面每次支持最多200个bulk样本；更大批次请使用冻结版命令行。输入未被截断。')
    c = r['column_type']
    preview = {'genes': len(r['genes']), 'samples': len(b['ids']), 'types': r['types'].astype(str).tolist(),
               'reference_profiles': int(r['F'].shape[1]),
               'reference_support': np.bincount(c, minlength=len(r['types'])).tolist(),
               'library_sizes': b['Y'].sum(0).astype(float).tolist(),
               'quantity': 'RNA_fraction_on_supplied_complete_input_gene_axis',
               'checks': checks, 'target_truth_read': False}
    save(job / 'input_preview.json', preview)
    del r, b, c
    gc.collect()
    save(phase, {'stage': 'fitting', 'updated': time.time()})
    code = frozen_main(['--reference', str(job / 'reference.npz'), '--bulk', str(job / 'bulk.npz'),
                        '--out', str(job / 'prediction')])
    save(phase, {'stage': 'complete' if code == 0 else 'uncertified', 'updated': time.time()})
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job-dir', required=True, type=Path)
    job = parser.parse_args().job_dir.resolve()
    try:
        raise SystemExit(run(job))
    except Exception as exc:
        save(job / 'phase.json', {'stage': 'failed', 'error': str(exc), 'updated': time.time()})
        raise
