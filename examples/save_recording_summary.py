"""Save a human-readable snapshot beside an existing recording database."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def save_summary(root, run_id=None, *, recent=5):
    from analog_optimizer.recording.reader import RunReader
    from analog_optimizer.recording.report import format_overview
    from analog_optimizer.recording.space import fsync_directory

    with RunReader(root) as reader:
        overview = reader.overview(run_id, recent=recent)
        recording_root = reader.root
    run_id = overview['run_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('Run ID must be a safe filename')
    directory = recording_root / 'summaries'
    if directory.is_symlink():
        raise ValueError('Summary directory must not be a symlink')
    directory.mkdir(exist_ok=True)
    destination = directory / (run_id + '.txt')
    if destination.is_symlink():
        raise ValueError('Summary file must not be a symlink')
    created = datetime.now(timezone.utc).isoformat(timespec='seconds')
    content = f'导出时间（UTC）: {created}\n静态快照；再次运行 summary 可读取最新记录。\n\n'
    content += format_overview(overview) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', dir=directory,
                                         prefix='.' + run_id + '-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
        fsync_directory(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def add_summary_to_report(root, run_id, report):
    """A derived text export must not hide a training/cleanup exception."""
    try:
        path = save_summary(root, run_id)
    except Exception as exc:
        report['summary_export_error'] = f'{type(exc).__name__}: {exc}'
        print('SUMMARY_EXPORT_FAILED', report['summary_export_error'], file=sys.stderr, flush=True)
    else:
        report['summary_path'] = str(path)
        print('SUMMARY', path, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--run')
    parser.add_argument('--recent', type=int, default=5)
    args = parser.parse_args()
    print(save_summary(args.root, args.run, recent=args.recent))


if __name__ == '__main__':
    main()
