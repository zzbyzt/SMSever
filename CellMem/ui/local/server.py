"""Loopback-only CellMem UI. User inputs and computation stay on this computer."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_file, send_from_directory, abort

BASE = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('CELLMEM_UI_RUNTIME', str(BASE.parent / 'runtime'))).resolve()
RUNS = RUNTIME / 'runs'
RUNS.mkdir(parents=True, exist_ok=True)
CORE_SHA = '47eaaa4fd87ed5513575cce025592824dcd1f5f8bbfb5f61c83389a3ea9a535d'
TOKEN = secrets.token_urlsafe(32)
app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 128 * 1024 * 1024
executor = ThreadPoolExecutor(max_workers=1)
lock = threading.Lock()
jobs = {}
allowed_downloads = {'predictions.tsv', 'predictions.npz', 'RUN_LOCK.json', 'PREDICTION_LOCK.json', 'NUMERICS.json'}


def dump(p, value):
    q = p.with_suffix('.pending')
    q.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    q.replace(p)


def environment():
    actual = {n: importlib.metadata.version(n) for n in ('numpy', 'scipy', 'flask')}
    core = BASE / 'method/src/cellmem_full_axis/_frozen_core.py'
    valid = core.exists() and hashlib.sha256(core.read_bytes()).hexdigest() == CORE_SHA
    provenance = json.loads((BASE / 'method/SOURCE_PROVENANCE.json').read_text(encoding='utf-8'))
    expected = [r for r in provenance['unchanged_files'] if r['path'].startswith('src/')]
    sources_valid = len(expected) == 6 and all(
        (BASE / 'method' / r['path']).is_file() and
        hashlib.sha256((BASE / 'method' / r['path']).read_bytes()).hexdigest() == r['sha256']
        for r in expected)
    return {'python': sys.version.split()[0], 'packages': actual, 'core_verified': valid,
            'runtime_sources_verified': sources_valid,
            'ready': valid and sources_valid and sys.version_info[:2] == (3, 11) and actual['numpy'] == '1.26.2' and actual['scipy'] == '1.11.4'}


@app.before_request
def local_only():
    if request.host.split(':')[0] not in {'127.0.0.1', 'localhost'}:
        abort(403)
    if request.method == 'POST':
        origin = request.headers.get('Origin')
        if origin and urlsplit(origin).netloc != request.host:
            abort(403)
        if not secrets.compare_digest(request.headers.get('X-CellMem-Token', ''), TOKEN):
            abort(403)


@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(413)
def too_large(_):
    return jsonify(error='两个输入文件合计超过128 MB。请使用冻结版命令行处理更大数据。'), 413


@app.get('/')
def index():
    return send_from_directory(BASE / 'dist', 'index.html')


@app.get('/<path:name>')
def static(name):
    if name.startswith('api/'):
        abort(404)
    return send_from_directory(BASE / 'dist', name)


@app.get('/api/health')
def health():
    return jsonify(app='cellmem-ui', method='FULL_DONOR_PRECISION', version='0.1.0',
                   token=TOKEN, environment=environment(), local_only=True,
                   limits={'upload_megabytes': 128, 'samples': 200, 'concurrent_runs': 1})


def check_npz(path):
    if not zipfile.is_zipfile(path):
        raise ValueError('输入必须是NPZ格式；不支持把CSV或H5AD直接改扩展名。')
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        if len(infos) > 50 or sum(i.file_size for i in infos) > 1024**3:
            raise ValueError('NPZ解压后超过1 GiB或字段过多。请使用命令行。')
        if any('/' in i.filename or '\\' in i.filename or not i.filename.endswith('.npy') for i in infos):
            raise ValueError('NPZ成员必须是顶层NumPy字段。')


def submit_job(is_demo, uploads=None):
    if not environment()['ready']:
        raise ValueError('环境或冻结核心校验失败，请按安装说明恢复Python 3.11与固定依赖。')
    with lock:
        if any(j['status'] in ('queued', 'running') for j in jobs.values()):
            return None
        jid = uuid.uuid4().hex
        folder = RUNS / jid
        folder.mkdir()
        meta = {'id': jid, 'status': 'queued', 'created': time.time(), 'demo': is_demo,
                'method': 'FULL_DONOR_PRECISION', 'target_truth_read': False}
        jobs[jid] = meta
    try:
        if is_demo:
            script = BASE / 'method/examples/make_synthetic_inputs.py'
            spec = importlib.util.spec_from_file_location('cellmem_ui_demo', script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            inputs = module.create(folder / 'synthetic_inputs')
            for name in ('reference.npz', 'bulk.npz'):
                (folder / name).write_bytes((inputs / name).read_bytes())
        else:
            for field in ('reference', 'bulk'):
                upload = uploads.get(field)
                if upload is None or not (upload.filename or '').lower().endswith('.npz'):
                    raise ValueError('请选择reference.npz和bulk.npz两个输入文件。')
                path = folder / (field + '.npz')
                upload.save(path)
                check_npz(path)
        dump(folder / 'job.json', meta)
        executor.submit(execute_job, jid)
        return meta
    except Exception as exc:
        meta.update(status='failed', error=str(exc), finished=time.time())
        dump(folder / 'job.json', meta)
        raise


def execute_job(jid):
    meta = jobs[jid]
    folder = RUNS / jid
    meta.update(status='running', started=time.time())
    dump(folder / 'job.json', meta)
    env = dict(os.environ)
    env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONUTF8='1')
    try:
        with (folder / 'run.log').open('w', encoding='utf-8') as log:
            process = subprocess.run([sys.executable, '-X', 'utf8', str(BASE / 'local/runner.py'),
                                      '--job-dir', str(folder)], stdout=log, stderr=log, env=env)
        predicted = (folder / 'prediction/PREDICTION_LOCK.json').exists()
        if process.returncode == 0 and predicted:
            meta['status'] = 'complete'
        elif process.returncode == 2 and predicted:
            meta['status'] = 'uncertified'
        else:
            meta['status'] = 'failed'
            phase = folder / 'phase.json'
            phase_value = json.loads(phase.read_text(encoding='utf-8')) if phase.exists() else {}
            meta['error'] = phase_value.get('error', (folder / 'run.log').read_text(encoding='utf-8')[-2000:])
        meta['exit_code'] = process.returncode
    except Exception as exc:
        meta.update(status='failed', error=str(exc))
    meta['finished'] = time.time()
    dump(folder / 'job.json', meta)


@app.post('/api/jobs')
def start_job():
    try:
        meta = submit_job(request.form.get('demo') == 'true', request.files)
        if meta is None:
            return jsonify(error='已有任务正在运行。当前界面一次运行一个任务。'), 409
        return jsonify(meta), 202
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        return jsonify(error=str(exc)), 400


def read_meta(jid):
    if len(jid) != 32 or any(c not in '0123456789abcdef' for c in jid):
        abort(404)
    folder = RUNS / jid
    if not (folder / 'job.json').exists():
        abort(404)
    meta = dict(jobs.get(jid) or json.loads((folder / 'job.json').read_text(encoding='utf-8')))
    if jid not in jobs and meta['status'] in ('queued', 'running'):
        meta.update(status='interrupted', error='服务重启前的任务未产生终态；结果未被当作完成。')
    for name in ('phase', 'input_preview'):
        p = folder / (name + '.json')
        if p.exists():
            meta[name] = json.loads(p.read_text(encoding='utf-8'))
    return meta, folder


@app.get('/api/jobs')
def list_jobs():
    values = []
    for p in sorted(RUNS.glob('*/job.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:50]:
        meta, _ = read_meta(p.parent.name)
        values.append(meta)
    return jsonify(jobs=values)


@app.get('/api/jobs/<jid>')
def get_job(jid):
    meta, folder = read_meta(jid)
    if meta['status'] in ('complete', 'uncertified'):
        import numpy as np
        with np.load(folder / 'prediction/predictions.npz', allow_pickle=False) as z:
            meta['result'] = {'ids': z['ids'].astype(str).tolist(), 'types': z['types'].astype(str).tolist(),
                              'prediction': z['prediction'].tolist(), 'genes': len(z['genes']),
                              'reference_support': z['reference_support'].tolist()}
        meta['numerics'] = json.loads((folder / 'prediction/NUMERICS.json').read_text(encoding='utf-8'))
        meta['prediction_lock'] = json.loads((folder / 'prediction/PREDICTION_LOCK.json').read_text(encoding='utf-8'))
    return jsonify(meta)


@app.get('/api/jobs/<jid>/download/<name>')
def download(jid, name):
    meta, folder = read_meta(jid)
    if meta['status'] not in ('complete', 'uncertified'):
        abort(409)
    if name == 'results.zip':
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(allowed_downloads):
                archive.write(folder / 'prediction' / item, item)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name='CellMem_' + jid[:8] + '_results.zip')
    if name not in allowed_downloads:
        abort(404)
    return send_file(folder / 'prediction' / name, as_attachment=True, download_name=name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default=8766, type=int)
    args = parser.parse_args()
    print('CellMem local UI: http://127.0.0.1:' + str(args.port), flush=True)
    app.run(host='127.0.0.1', port=args.port, debug=False, threaded=True, use_reloader=False)
