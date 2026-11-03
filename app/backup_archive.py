"""Offline, checksummed data-volume archives; never import the running app."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tarfile
import tempfile

from .storage import write_json_atomic


def _hash(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _validate_data(root: Path) -> dict:
    counts = {'json_files': 0, 'sqlite_databases': 0}
    if not (root / 'ai-news/articles.json').is_file():
        raise ValueError('Missing ai-news/articles.json; use the entire data root')
    for path in root.rglob('*'):
        if path.suffix == '.json' and path.is_file():
            json.loads(path.read_text(encoding='utf-8'))
            counts['json_files'] += 1
        if path.suffix == '.db' and path.is_file():
            # SQLite can update SHM even on a read-only connection. Validate a
            # disposable copy, including WAL, without changing snapshot bytes.
            with tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / path.name
                for suffix in ('', '-wal', '-shm'):
                    source = Path(str(path) + suffix)
                    if source.exists():
                        shutil.copyfile(source, Path(str(target) + suffix))
                with sqlite3.connect(target.as_uri() + '?mode=ro', uri=True) as db:
                    if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                        raise ValueError('SQLite integrity check failed')
            counts['sqlite_databases'] += 1
    return counts


def create_backup(source: Path, archive: Path) -> dict:
    """Source MUST be a stopped-app snapshot, not a live data directory."""
    source, archive = source.resolve(), archive.absolute()
    if archive.is_relative_to(source):
        raise ValueError('Archive must be outside the source directory')
    files, directories = {}, []
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source).as_posix()
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('Backup source contains links or special files')
        if path.is_dir():
            directories.append(relative)
        else:
            files[relative] = {'size': path.stat().st_size, 'sha256': _hash(path)}
    counts = _validate_data(source)
    manifest = {'format': 'aif-data-v1', 'created_at': datetime.now(timezone.utc).isoformat(),
                'files': files, 'directories': directories}
    # Exclusive creation refuses to overwrite a previous backup; mode is private
    # from the first byte, regardless of the caller's umask.
    descriptor = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as output, tempfile.TemporaryDirectory() as temp:
            manifest_path = Path(temp) / 'manifest.json'
            write_json_atomic(manifest_path, manifest)
            with tarfile.open(fileobj=output, mode='w:gz') as tar:
                tar.add(manifest_path, arcname='manifest.json')
                for relative in directories:
                    tar.add(source / relative, arcname='data/' + relative, recursive=False)
                for relative in files:
                    tar.add(source / relative, arcname='data/' + relative, recursive=False)
            output.flush()
            os.fsync(output.fileno())
        verify_backup(archive)
    except BaseException:
        archive.unlink(missing_ok=True)
        raise
    return {'files': len(files), **counts}


def _relative(name: str) -> str:
    path = PurePosixPath(name)
    if not path.parts or '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts or str(path) != name:
        raise ValueError('Unsafe archive path')
    return name


def _unpack(archive: Path, destination: Path) -> dict:
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        names = [item.name for item in members]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate archive members')
        if any(not (item.isfile() or item.isdir()) for item in members):
            raise ValueError('Archive links and special files are forbidden')
        header = tar.getmember('manifest.json')
        if not header.isfile() or header.size > 16 * 1024 * 1024:
            raise ValueError('Invalid manifest')
        manifest = json.load(tar.extractfile(header))
        if manifest.get('format') != 'aif-data-v1':
            raise ValueError('Unsupported backup format')
        files, directories = manifest['files'], manifest['directories']
        expected = {'manifest.json'}
        for relative in [*directories, *files]:
            expected.add('data/' + _relative(relative))
        if set(names) != expected:
            raise ValueError('Archive member inventory mismatch')
        for relative in directories:
            item = tar.getmember('data/' + relative)
            if not item.isdir():
                raise ValueError('Invalid directory member')
            (destination / relative).mkdir(parents=True, exist_ok=True, mode=0o700)
        for relative, record in files.items():
            item = tar.getmember('data/' + relative)
            if not item.isfile() or item.size != record['size']:
                raise ValueError('File size mismatch')
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with target.open('xb') as output:
                os.chmod(target, 0o600)
                shutil.copyfileobj(tar.extractfile(item), output)
            if _hash(target) != record['sha256']:
                raise ValueError('File checksum mismatch')
    return {'files': len(files), **_validate_data(destination)}


def verify_backup(archive: Path) -> dict:
    with tempfile.TemporaryDirectory() as temp:
        return _unpack(archive, Path(temp))


def restore_backup(archive: Path, destination: Path) -> dict:
    """Publish only a verified tree into a new path; never overwrite live data."""
    if destination.exists() or destination.is_symlink():
        raise ValueError('Restore destination must not exist')
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.aif-restore-') as temp:
        staging = Path(temp) / 'data'
        staging.mkdir(mode=0o700)
        counts = _unpack(archive, staging)
        # Reserve the destination exclusively after verification, preventing a
        # concurrent restore from replacing another directory.
        destination.mkdir(mode=0o700)
        try:
            for item in staging.iterdir():
                shutil.move(str(item), destination / item.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return counts
