"""Private saved transcripts. Session identifiers never become arbitrary paths."""
import json
import os
import re
import secrets
import threading
import time
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path

_LOCKS = {}
_REGISTRY_LOCK = threading.Lock()
def locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.lock: return method(self, *args, **kwargs)
    return call

class SessionStore:
    def __init__(self, root):
        self.root = Path(root)
        with _REGISTRY_LOCK:
            self.lock = _LOCKS.setdefault(self.root.resolve(), threading.RLock())

    def paths(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{32}', identity):
            raise ValueError('Sesión inválida')
        return self.root / (identity + '.json'), self.root / (identity + '.txt')

    @locked
    def read(self, identity):
        metadata, transcript = self.paths(identity)
        if metadata.is_symlink() or transcript.is_symlink():
            raise ValueError('Sesión inválida')
        if metadata.stat().st_size > 65536:
            raise ValueError('Metadatos demasiado grandes')
        data = json.loads(metadata.read_text(encoding="utf-8"))
        if not isinstance(data,dict) or not isinstance(data.get('config'),dict) or any(not isinstance(data.get(k),str) for k in ('name','created','updated')):
            raise ValueError('Metadatos inválidos')
        if data.get('id') != identity or not transcript.is_file():
            raise ValueError('Sesión incompleta')
        return data

    @locked
    def write(self, data):
        metadata, _ = self.paths(data['id'])
        temporary = metadata.with_name(metadata.name+'.'+secrets.token_hex(8)+'.tmp')
        if temporary.is_symlink() or metadata.is_symlink():
            raise ValueError('Sesión inválida')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(data, output, ensure_ascii=False)
        try:
            for attempt in range(5):
                try:
                    os.replace(temporary, metadata); break
                except PermissionError:
                    if os.name != 'nt' or attempt == 4: raise
                    time.sleep(.02 * (2**attempt))
        finally:
            if temporary.exists(): temporary.unlink()

    def name(self, value):
        if not isinstance(value, str) or len(value) > 120 or any(ord(c) < 32 for c in value):
            raise ValueError('Nombre inválido')
        return value.strip()

    @locked
    def create(self, name, config):
        name = self.name(name)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        identity = secrets.token_hex(16)
        stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        data = dict(id=identity, name=name or 'Sesión ' + stamp, created=stamp,
                    updated=stamp, config=config)
        _, transcript = self.paths(identity)
        transcript.touch(mode=0o600, exist_ok=False)
        self.write(data)
        return data

    @locked
    def resume(self, identity, config):
        data = self.read(identity)
        data['updated'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        data['config'] = config
        self.write(data)
        return data

    @locked
    def rename(self, identity, name):
        data = self.read(identity)
        data['name'] = self.name(name)
        if not data['name']:
            raise ValueError('Nombre vacío')
        self.write(data)
        return data

    @locked
    def list(self):
        result = []
        if not self.root.exists():
            return result
        for metadata in self.root.glob('*.json'):
            try:
                data = self.read(metadata.stem)
                result.append({k: data[k] for k in ('id', 'name', 'created', 'updated')})
            except (ValueError, OSError, KeyError):
                continue
        return sorted(result, key=lambda item: item['updated'], reverse=True)

    @locked
    def content(self, identity):
        data = self.read(identity)
        _, transcript = self.paths(identity)
        with transcript.open('rb') as source:
            source.seek(max(0, transcript.stat().st_size - 2_000_000))
            text = source.read().decode('utf-8', errors='replace')
        return dict(metadata=data, transcript=text, truncated=transcript.stat().st_size > 2_000_000)
