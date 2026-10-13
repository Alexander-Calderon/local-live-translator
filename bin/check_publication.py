"""Inspect Git candidates locally. Print reasons and paths, never matched contents."""
import hashlib
import argparse
import os
from pathlib import Path
import re
import subprocess

ROOT_FILES = {'.gitignore', 'README.md', 'LICENSE', 'LICENSE.md', 'run.sh', 'app.sh', 'install.sh',
              'requirements.txt', 'CONTRIBUTING.md', 'SECURITY.md', 'CHANGELOG.md', 'VERSION', 'install.py', 'app.cmd'}
PUBLIC_MEDIA = {'docs/media/translator-flow.mp4': '6de1dc82744f999fecadef6172d2f4aa81b96ea4804443da334f0a0370af0c16', 'docs/media/translator-flow.gif': '4cab9e03628b312529ba49e9e39bde3c45f953ad27ec3594e9625fef3b66ac31', 'docs/media/poster.png': 'b7f99f22ba899c209f29408db6036e8d341904297adeef456b70b85fc86718ab'}

RULES = {
    'ruta personal absoluta': re.compile(r'/(?:home|Users|mnt/data)/[^\s\"\']+'),
    'clave privada': re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----'),
    'credencial de proveedor': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9_-]{24,}|AKIA[A-Z0-9]{16})\b'),
    'URL con credenciales': re.compile(r'https?://[^\s/:]+:[^\s/@]+@'),
    'URL privada de una sesión del visor': re.compile(r'https?://(?:127\.0\.0\.1|localhost):\d{2,5}/[A-Za-z0-9_-]{24,}'),
    'correo personal': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
}

def allowed(path):
    path = Path(path)
    name = path.as_posix()
    if name in PUBLIC_MEDIA:
        return True
    if name == 'docs/streaming-corpus.json':
        return True
    if name == 'bin/resumir.sh':
        return False
    if name in ROOT_FILES:
        return True
    if name in {'vocab/tech-example.txt','vocab/tech-aliases.json'}:
        return True
    if len(path.parts) != 2:
        return name == '.github/workflows/test.yml'
    return (path.parts[0] in {'bin', 'tests'} and path.suffix in {'.py', '.sh'}
            or path.parts[0] == 'docs' and path.suffix == '.md')

def findings(root, paths):
    issues = []
    for relative in sorted(set(paths)):
        path = root / relative
        if not allowed(relative):
            issues.append((relative, 'archivo fuera de la lista publicable'))
            continue
        if path.is_symlink():
            issues.append((relative, 'enlace simbólico'))
            continue
        if not path.is_file():
            issues.append((relative, 'archivo ausente'))
            continue
        if path.stat().st_size > 1_000_000:
            issues.append((relative, 'archivo mayor de 1 MB'))
            continue
        if relative in PUBLIC_MEDIA:
            if hashlib.sha256(path.read_bytes()).hexdigest() != PUBLIC_MEDIA[relative]:
                issues.append((relative, 'medio distinto del artefacto revisado'))
            continue
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeError:
            issues.append((relative, 'contenido binario'))
            continue
        for reason, pattern in RULES.items():
            if pattern.search(content):
                issues.append((relative, reason))
    return issues

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--tracked-only', action='store_true', help='CI: revisar solo archivos versionados')
    args = parser.parse_args()
    root = args.root.resolve()
    env = dict(os.environ)
    # Antes de git init: simular el índice en un directorio temporal externo.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='publication-index-') as temporary:
        probe = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                               capture_output=True, text=True, env=env)
        if probe.returncode or Path(probe.stdout.strip()).resolve() != root:
            if args.tracked_only:
                parser.error('--tracked-only requiere el repositorio del proyecto')
            subprocess.run(['git', 'init', '--bare', '--quiet', temporary], check=True)
            env.update(GIT_DIR=temporary, GIT_WORK_TREE=str(root))
        command = ['git', '-c', 'core.excludesfile=/dev/null', '-C', str(root), 'ls-files', '-z', '--cached']
        if not args.tracked_only:
            command += ['--others', '--exclude-standard']
        result = subprocess.run(command, capture_output=True, check=True, env=env)
        paths = [os.fsdecode(path) for path in result.stdout.split(b'\0') if path]
    issues = findings(root, paths)
    for path, reason in issues:
        print(f'REVISAR {path}: {reason}')
    print(f'{len(paths)} archivos revisados; {len(issues)} hallazgos. No se imprimen contenidos privados.')
    if issues:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
