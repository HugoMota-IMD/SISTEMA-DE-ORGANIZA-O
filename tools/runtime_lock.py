"""Project-local process locks; no database, networking or privileged operations."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time


def instance_id(root):
    return hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()[:16]


def runtime_directory(root):
    directory = Path(root).resolve() / 'data' / 'runtime'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@contextmanager
def exclusive_lock(path, timeout=0):
    """OS releases this lock even if a Windows process is forcibly terminated."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+b')
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b'0')
        handle.flush()
    deadline = time.monotonic() + timeout
    acquired = False
    try:
        while True:
            handle.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('O Organiza já está iniciando, funcionando ou sendo encerrado nesta porta.') from None
                time.sleep(.1)
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def metadata_path(root, port):
    return runtime_directory(root) / f'server-{port}.json'


@contextmanager
def server_guard(root, port):
    """Wrap the complete Waitress lifetime, including bind and shutdown."""
    root = Path(root).resolve()
    directory = runtime_directory(root)
    with exclusive_lock(directory / f'server-{port}.lock'):
        database = Path(os.getenv('APP_DB_PATH', str(root / 'data' / 'finance.sqlite3')))
        if not database.is_absolute():
            database = root / database
        metadata = {'pid': os.getpid(), 'instance_id': instance_id(root), 'port': port,
                    'database_path': str(database.resolve()),
                    'started_at': datetime.now(timezone.utc).isoformat()}
        target = metadata_path(root, port)
        temporary = target.with_suffix(f'.{os.getpid()}.tmp')
        temporary.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        temporary.replace(target)
        try:
            yield
        finally:
            try:
                saved = json.loads(target.read_text(encoding='utf-8'))
                if saved.get('pid') == os.getpid():
                    target.unlink()
            except (OSError, ValueError):
                pass
