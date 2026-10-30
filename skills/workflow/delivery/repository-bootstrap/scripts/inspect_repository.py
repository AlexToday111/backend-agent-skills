"""Print facts without source contents, credentials or Git remote URLs."""
import argparse
from pathlib import Path
import sys
from bootstrap import dump, inspect

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    try:
        print(dump(inspect(args.root)), end='')
    except (OSError, ValueError) as exc:
        print(f'Inspection failed ({type(exc).__name__})', file=sys.stderr)
        sys.exit(1)
