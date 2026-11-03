"""Backup integrity, WAL preservation and non-destructive restore boundaries."""
import io
import json
from pathlib import Path
import sqlite3
import tarfile

import pytest

from app.backup_archive import create_backup, restore_backup, verify_backup
from app.storage import write_json_atomic


@pytest.fixture
def data(tmp_path):
    root = tmp_path / 'source'
    write_json_atomic(root / 'ai-news/articles.json', [{'id': 'a_test'}])
    write_json_atomic(root / 'auth/users.json', [{'id': 'u_test', 'role': 'admin'}])
    write_json_atomic(root / 'users/u_test/pins.json', ['a_test'])
    write_json_atomic(root / 'users/u_test/experiments/a_test.json', {'status': 'done', 'notes': 'fixture'})
    write_json_atomic(root / 'ai-news/coverage-benchmarks.json', [{'evidence': {'matched_at': '2026-11-03'}}])
    (root / 'users/_legacy').mkdir()
    return root


def test_roundtrip_preserves_every_file_and_empty_directory(data, tmp_path):
    archive = tmp_path / 'backup.aif-backup.tar.gz'
    result = create_backup(data, archive)
    assert archive.stat().st_mode & 0o777 == 0o600
    assert result == verify_backup(archive)
    restored = tmp_path / 'restored'
    assert restore_backup(archive, restored) == result
    before = {p.relative_to(data): p.read_bytes() for p in data.rglob('*') if p.is_file()}
    after = {p.relative_to(restored): p.read_bytes() for p in restored.rglob('*') if p.is_file()}
    assert before == after
    assert (restored / 'users/_legacy').is_dir()


def test_committed_sqlite_wal_rows_survive_backup(data, tmp_path):
    path = data / 'users/u_test/ui.db'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE messages (body TEXT)')
        db.commit()
        db.execute("INSERT INTO messages VALUES ('fixture conversation')")
        db.commit()
        assert Path(str(path) + '-wal').stat().st_size > 0
        archive = tmp_path / 'wal.aif-backup.tar.gz'
        create_backup(data, archive)
        restore_backup(archive, tmp_path / 'restored')
    with sqlite3.connect(tmp_path / 'restored/users/u_test/ui.db') as db:
        assert db.execute('SELECT body FROM messages').fetchall() == [('fixture conversation',)]


def test_refuses_overwrite_and_live_directory_restore(data, tmp_path):
    archive = tmp_path / 'backup.aif-backup.tar.gz'
    create_backup(data, archive)
    original = archive.read_bytes()
    with pytest.raises(FileExistsError):
        create_backup(data, archive)
    assert archive.read_bytes() == original
    with pytest.raises(ValueError, match='must not exist'):
        restore_backup(archive, data)
    assert (data / 'ai-news/articles.json').exists()
    with pytest.raises(ValueError, match='outside'):
        create_backup(data, data / 'backup.tar.gz')


def test_rejects_symlink_and_corrupt_json(data, tmp_path):
    (data / 'link').symlink_to(tmp_path)
    with pytest.raises(ValueError, match='links'):
        create_backup(data, tmp_path / 'link.tar.gz')
    (data / 'link').unlink()
    (data / 'ai-news/articles.json').write_text('{broken')
    with pytest.raises(ValueError):
        create_backup(data, tmp_path / 'broken.tar.gz')
    assert not (tmp_path / 'broken.tar.gz').exists()


@pytest.mark.parametrize('attack', ['tamper', 'traversal', 'symlink', 'extra', 'duplicate'])
def test_rejects_modified_or_unsafe_archives_without_publishing(data, tmp_path, attack):
    good, bad = tmp_path / 'good.tar.gz', tmp_path / 'bad.tar.gz'
    create_backup(data, good)
    with tarfile.open(good) as source, tarfile.open(bad, 'w:gz') as target:
        for member in source.getmembers():
            body = source.extractfile(member).read() if member.isfile() else None
            if attack == 'tamper' and member.name == 'data/users/u_test/pins.json':
                body = b' ' * len(body)
            target.addfile(member, io.BytesIO(body) if body is not None else None)
        if attack != 'tamper':
            name = {'traversal': 'data/../../escape', 'symlink': 'data/link',
                    'extra': 'data/unlisted', 'duplicate': 'manifest.json'}[attack]
            member = tarfile.TarInfo(name)
            if attack == 'symlink':
                member.type, member.linkname = tarfile.SYMTYPE, '/tmp'
            target.addfile(member, io.BytesIO(b''))
    restored = tmp_path / 'restored'
    with pytest.raises((ValueError, KeyError)):
        restore_backup(bad, restored)
    assert not restored.exists()
    assert not (tmp_path / 'escape').exists()


def test_cli_reports_truncated_archive_without_dumping_data(data, tmp_path):
    import subprocess
    import sys

    archive = tmp_path / 'truncated.tar.gz'
    create_backup(data, archive)
    archive.write_bytes(archive.read_bytes()[:20])
    result = subprocess.run(
        [sys.executable, '-m', 'app.backup', 'verify', '--archive', str(archive)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'no verified result' in result.stderr
    assert 'Traceback' not in result.stderr
    assert not result.stdout
