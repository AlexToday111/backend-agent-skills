"""Apply twice to a temporary copy; never modify the source."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
from bootstrap import apply, dump, plan, EXCLUDED, linked


def snapshot(root):
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != '.git' and not linked(Path(directory, d)))
        for name in sorted(files):
            path = Path(directory, name)
            if not linked(path) and path.is_file():
                result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def check(root, **options):
    root = root.resolve()
    # Removing links from the copy must not turn source conflicts into success.
    source_plan = plan(root, **options)
    with tempfile.TemporaryDirectory(prefix='bootstrap-idempotency-') as temp:
        target = Path(temp) / 'repository'
        def ignore(directory, names):
            return [n for n in names if n in EXCLUDED or linked(Path(directory, n))
                    or (Path(directory, n).is_dir() and Path(directory, n, '.git').exists())]
        shutil.copytree(root, target, ignore=ignore)
        first = apply(target, plan(target, **options))
        before = snapshot(target)
        second = apply(target, plan(target, **options))
        return {'idempotent': before == snapshot(target) and not second['applied'],
                'first_applied': first['applied'], 'second_applied': second['applied'],
                'validation': second['validation'], 'first_validation': first['validation'],
                'conflicts': sorted({o['path'] for report in (source_plan, first, second)
                                     for o in report['operations'] if o['action'] == 'CONFLICT'})}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--java-version')
    parser.add_argument('--java-distribution', choices=['temurin', 'zulu', 'corretto', 'microsoft', 'oracle'])
    args = parser.parse_args()
    try:
        result = check(args.root.resolve(), java_version=args.java_version,
                       java_distribution=args.java_distribution)
        print(dump(result), end='')
        failed = not result['idempotent'] or any(result[k]['status'] != 'passed'
                    for k in ('validation', 'first_validation'))
        sys.exit(1 if failed else 2 if result['conflicts'] else 0)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Idempotency check failed ({type(exc).__name__})\n')
