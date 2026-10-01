"""Empacota bibliotecas locais de captura. Não envia documentos a CDNs.

Antes: npm ci --prefix .local/captura-deps --ignore-scripts --no-audit
Versões e hashes do resultado: static/vendor/captura-v1/versions.json.
"""
from pathlib import Path
import hashlib
import json
import shutil

src = Path('.local/captura-deps/node_modules')
dst = Path('static/vendor/captura-v1')
dst.mkdir(parents=True, exist_ok=True)
items = {
    'tesseract.js/dist/tesseract.min.js': 'tesseract.min.js',
    'tesseract.js/dist/worker.min.js': 'worker.min.js',
    'zxing-wasm/dist/iife/reader/index.js': 'zxing-reader.js',
    'zxing-wasm/dist/reader/zxing_reader.wasm': 'zxing_reader.wasm',
    'pdfjs-dist/build/pdf.mjs': 'pdf.mjs',
    'pdfjs-dist/build/pdf.worker.mjs': 'pdf.worker.mjs',
    '@tesseract.js-data/por/4.0.0_best_int/por.traineddata.gz': 'lang/por.traineddata.gz',
}
for f in (src / 'tesseract.js-core').glob('*.wasm.js'):
    items[f.relative_to(src).as_posix()] = 'core/' + f.name
for origem, destino in items.items():
    target = dst / destino
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src / origem, target)
for directory, target in [('pdfjs-dist/cmaps', 'cmaps'), ('pdfjs-dist/standard_fonts', 'standard_fonts'), ('pdfjs-dist/wasm', 'pdf-wasm')]:
    shutil.copytree(src / directory, dst / target, dirs_exist_ok=True)
versions = {}
for package in ['tesseract.js', 'tesseract.js-core', 'zxing-wasm', 'pdfjs-dist', '@tesseract.js-data/por']:
    versions[package] = json.loads((src / package / 'package.json').read_text())['version']
    for f in (src / package).iterdir():
        if f.is_file() and f.name.lower().startswith(('license', 'copying', 'notice')):
            shutil.copyfile(f, dst / (package.replace('/', '-').replace('@', '') + '-' + f.name))
manifest = {f.relative_to(dst).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in dst.rglob('*') if f.is_file() and f.name != 'versions.json'}
(dst / 'versions.json').write_text(json.dumps({'versions': versions, 'sha256': manifest}, indent=2), encoding='utf-8')
print(versions)
print('Total MB:', round(sum(f.stat().st_size for f in dst.rglob('*') if f.is_file()) / 1024 / 1024, 1))
