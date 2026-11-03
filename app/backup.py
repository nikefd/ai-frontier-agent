"""python -m app.backup: offline data-volume backup, verification and restore."""
import argparse
import json
import sqlite3
import tarfile
from pathlib import Path

from .backup_archive import create_backup, restore_backup, verify_backup


def main() -> None:
    parser = argparse.ArgumentParser(description='Offline AI Frontier data backups (contains private data)')
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create')
    create.add_argument('--source', type=Path, required=True)
    create.add_argument('--archive', type=Path, required=True)
    create.add_argument('--offline-snapshot', action='store_true', required=True,
                        help='Confirm source was copied while the app was stopped')
    verify = commands.add_parser('verify')
    verify.add_argument('--archive', type=Path, required=True)
    restore = commands.add_parser('restore')
    restore.add_argument('--archive', type=Path, required=True)
    restore.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'create':
            result = create_backup(args.source, args.archive)
        elif args.command == 'verify':
            result = verify_backup(args.archive)
        else:
            result = restore_backup(args.archive, args.destination)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, tarfile.TarError) as error:
        # No file contents, emails or credentials in command output.
        parser.exit(1, f'Backup operation failed ({type(error).__name__}); no verified result.\n')
    print(json.dumps({'ok': True, **result}))


if __name__ == '__main__':
    main()
