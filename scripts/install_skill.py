"""Copy a catalogued skill flat under an explicit discovery directory."""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat


def reject_links(source):
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(directory, name)
            attributes = getattr(path.lstat(), 'st_file_attributes', 0)
            if path.is_symlink() or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError('Skill sources must contain only real files and directories')


def install(name, destination):
    root = Path(__file__).resolve().parent.parent
    document = json.loads((root / 'skills.json').read_text(encoding='utf-8'))
    if (not isinstance(document, dict) or type(document.get('schema_version')) is not int
            or document['schema_version'] != 1
            or not isinstance(document.get('skills'), dict)):
        raise ValueError('Invalid skill catalog')
    catalog = document['skills']
    if name not in catalog:
        raise ValueError('Unknown or unimplemented skill: ' + name)
    relative = catalog[name]
    if not isinstance(relative, str) or not relative:
        raise ValueError('Invalid catalog path')
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != 'skills':
        raise ValueError('Invalid catalog path')
    source = root / relative
    # Check before resolving, which would conceal linked source directories.
    for parent in (source, *source.parents):
        if parent == root:
            break
        attributes = getattr(parent.lstat(), 'st_file_attributes', 0)
        if parent.is_symlink() or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Linked skill source requires manual review')
    source = source.resolve()
    if not source.is_relative_to(root) or source.name != name:
        raise ValueError('Invalid catalog entry')
    destination = Path(destination)
    target = destination / name
    if target.exists() or target.is_symlink():
        raise ValueError('Destination already exists; review before reinstalling')
    if destination.resolve().is_relative_to(source):
        raise ValueError('Cannot install inside the skill source')
    reject_links(source)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name')
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(install(args.name, args.destination))
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')
