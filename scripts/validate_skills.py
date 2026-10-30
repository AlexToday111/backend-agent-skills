"""Validate the skill catalog and resources without executing inspected scripts."""
import json
import os
from pathlib import Path
import re
import stat
import sys

try:
    import yaml
except ImportError:
    yaml = None

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def parse_document(body):
    try:
        return json.loads(body, object_pairs_hook=unique_json)
    except json.JSONDecodeError:
        if yaml is None:
            raise ImportError('PyYAML unavailable')
        class UniqueLoader(yaml.SafeLoader):
            pass

        def mapping(loader, node):
            result = {}
            for key_node, value_node in node.value:
                key = loader.construct_object(key_node)
                if key in result:
                    raise ValueError('Duplicate YAML key')
                result[key] = loader.construct_object(value_node)
            return result

        UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        return yaml.load(body, Loader=UniqueLoader)


def real_resource(root, relative):
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts:
        raise ValueError('Resource path must be relative')
    path = root / rel
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Resource escapes its root')
    for part in (path, *path.parents):
        if part == root:
            break
        attributes = getattr(part.lstat(), 'st_file_attributes', 0)
        if part.is_symlink() or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Linked resource requires manual review')
    return path


def resources(root):
    """Enumerate real directories without descending into Windows junctions."""
    for directory, dirs, files in os.walk(root, followlinks=False):
        real_dirs = []
        for name in sorted(dirs + files):
            path = Path(directory, name)
            yield path
            if name in dirs:
                attributes = getattr(path.lstat(), 'st_file_attributes', 0)
                if not path.is_symlink() and not attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    real_dirs.append(name)
        dirs[:] = real_dirs


def validate_metadata(metadata, name):
    allowed = {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'}
    if not isinstance(metadata, dict) or set(metadata) - allowed:
        raise ValueError('Unknown metadata fields or invalid frontmatter mapping')
    if metadata.get('name') != name:
        raise ValueError('Name must match skill directory')
    for field, limit in (('description', 1024), ('compatibility', 500)):
        if field == 'compatibility' and field not in metadata:
            continue
        value = metadata.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError('Invalid ' + field)
    values = metadata.get('metadata', {})
    if not isinstance(values, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()):
        raise ValueError('Metadata must map strings to strings')
    for field in ('license', 'allowed-tools'):
        if field in metadata and not isinstance(metadata[field], str):
            raise ValueError('Invalid ' + field)


def validate_repository(root):
    root = Path(root).resolve()
    errors, unverified, checked = [], [], []

    def result():
        return {'status': 'failed' if errors else 'partial' if unverified else 'passed',
                'errors': errors, 'unverified': unverified, 'checked': checked}

    try:
        catalog = json.loads((root / 'skills.json').read_text(encoding='utf-8'),
                             object_pairs_hook=unique_json)
        if (not isinstance(catalog, dict) or type(catalog.get('schema_version')) is not int
                or catalog['schema_version'] != 1 or not isinstance(catalog.get('skills'), dict)):
            raise ValueError('Invalid skill catalog')
        entries = catalog['skills']
        if any(not isinstance(rel, str) for rel in entries.values()):
            raise ValueError('Catalog paths must be strings')
        discovered = {p.parent.relative_to(root).as_posix()
                      for p in resources(root / 'skills') if p.name == 'SKILL.md'}
        if discovered != set(entries.values()) or len(entries) != len(set(entries.values())):
            errors.append('Catalog and discovered skill directories differ')
        checked.append('skills.json')
    except Exception as exc:
        errors.append(f'Catalog validation failed ({type(exc).__name__})')
        return result()

    for name, rel in entries.items():
        try:
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or len(name) > 64:
                raise ValueError('Invalid skill name')
            directory = real_resource(root, rel)
            if directory.name != name or not directory.is_relative_to(root / 'skills'):
                raise ValueError('Catalog path/name mismatch')
            body = real_resource(directory, 'SKILL.md').read_text(encoding='utf-8')
            frontmatter = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)', body, re.S)
            if frontmatter is None:
                raise ValueError('Missing frontmatter')
            try:
                validate_metadata(parse_document(frontmatter.group(1)), name)
            except ImportError:
                unverified.append(rel + '/SKILL.md: install requirements-validation.txt for metadata validation')
            # Check references and unused assets too; do not import skill code.
            for resource in resources(directory):
                relative = resource.relative_to(root).as_posix()
                real_resource(directory, resource.relative_to(directory))
                if not resource.is_file():
                    continue
                try:
                    if resource.suffix == '.md':
                        for ref in re.findall(r'\]\(([^)]+)\)', resource.read_text(encoding='utf-8')):
                            if '://' in ref or ref.startswith(('#', 'mailto:')):
                                continue
                            link = ref.split('#')[0]
                            target_rel = (resource.parent / link).relative_to(directory)
                            if not real_resource(directory, target_rel).is_file():
                                raise ValueError('Broken resource link')
                    elif resource.suffix == '.py':
                        compile(resource.read_text(encoding='utf-8-sig'), relative, 'exec')
                    elif resource.suffix in {'.yml', '.yaml'}:
                        parse_document(resource.read_text(encoding='utf-8'))
                    checked.append(relative)
                except ImportError:
                    unverified.append(relative + ': install requirements-validation.txt for YAML validation')
                except Exception as exc:
                    errors.append(f'{relative}: resource validation failed ({type(exc).__name__})')
        except Exception as exc:
            # Parser exceptions may contain source excerpts; expose only their type.
            errors.append(f'{rel}: skill validation failed ({type(exc).__name__})')

    repository_resources = [p for p in resources(root / '.github') if p.suffix in {'.yml', '.yaml'}]
    repository_resources += sorted((root / 'scripts').glob('*.py'))
    for resource in repository_resources:
        relative = resource.relative_to(root).as_posix()
        try:
            real_resource(root, relative)
            body = resource.read_text(encoding='utf-8-sig')
            if resource.suffix == '.py':
                compile(body, relative, 'exec')
            else:
                parse_document(body)
            checked.append(relative)
        except ImportError:
            unverified.append(relative + ': install requirements-validation.txt for YAML validation')
        except Exception as exc:
            errors.append(f'{relative}: resource validation failed ({type(exc).__name__})')
    return result()


if __name__ == '__main__':
    report = validate_repository(ROOT)
    print(json.dumps(report, indent=2))
    sys.exit(0 if report['status'] == 'passed' else 1)
