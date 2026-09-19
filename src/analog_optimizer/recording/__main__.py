import argparse
import json
from pathlib import Path

from .codec import tree
from .reader import RunReader
from .space import disk_bytes


def main():
    parser = argparse.ArgumentParser(description='Inspect GATOR experiment records (no simulation)')
    parser.add_argument('root', type=Path)
    parser.add_argument('command', choices=('runs', 'show', 'summary', 'pending', 'usage', 'export'))
    parser.add_argument('--run')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--recent', type=int, default=5, help='Recent evaluations shown by summary, 0..100')
    parser.add_argument('--json', action='store_true', help='Machine-readable summary (other commands already use JSON)')
    args = parser.parse_args()
    with RunReader(args.root) as reader:
        if args.command == 'summary':
            try:
                value = reader.overview(args.run, recent=args.recent)
            except (KeyError, ValueError) as exc:
                parser.error(str(exc))
            if not args.json:
                from .report import format_overview
                print(format_overview(value))
                return
        elif args.command == 'usage':
            value = {name: disk_bytes(reader.root / name) for name in
                     ('experiments.sqlite3', 'experiments.sqlite3-wal', 'experiments.sqlite3-shm',
                      'experiments.sqlite3-journal', 'attachments', 'checkpoints', 'temporary')}
        elif args.command == 'runs':
            value = [dict(id=row['id'], started=row['started'], ended=row['ended']) for row in reader.call('read', 'runs')]
        elif args.command == 'pending':
            value = reader.call('pending', args.run)
        elif args.command == 'export':
            if not args.run or not args.output:
                parser.error('export requires --run and --output')
            value = str(reader.export(args.run, args.output))
        else:
            if not args.run:
                parser.error('show requires --run')
            row = reader.call('read', 'run', args.run)
            value = {key: row[key] for key in ('id', 'config_id', 'started', 'ended', 'summary', 'pending')}
        def display(value):
            if isinstance(value, dict):
                return {('/'.join(key) if isinstance(key, tuple) else str(key)): display(val) for key, val in value.items()}
            if isinstance(value, (list, tuple)):
                return [display(val) for val in value]
            return value
        print(json.dumps(display(value), ensure_ascii=False, indent=2, default=lambda x: tree(x)))


if __name__ == '__main__':
    main()
