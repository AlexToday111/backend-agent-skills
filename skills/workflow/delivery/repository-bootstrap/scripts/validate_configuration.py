"""Structural checks, not complete GitHub schema or application verification."""
from __future__ import annotations
import argparse
import configparser
import json
from pathlib import Path
import sys


def parse_yaml(body):
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Duplicate JSON key')
                result[key] = value
            return result
        return json.loads(body, object_pairs_hook=unique)
    except json.JSONDecodeError:
        import yaml
        class UniqueLoader(yaml.BaseLoader):
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


def validate(root, paths=None):
    from bootstrap import safe_path, inspect
    errors, unverified, checked = [], [], []
    if paths is None:
        paths = inspect(root)['existing_configuration']
    for rel in sorted(set(paths)):
        try:
            p = safe_path(root, rel)
            body = p.read_text(encoding='utf-8-sig')
            if not body.strip():
                raise ValueError('Empty configuration')
            if rel.endswith(('.yml', '.yaml')):
                try:
                    data = parse_yaml(body)
                except ImportError:
                    unverified.append(f'{rel}: install PyYAML for non-JSON YAML validation')
                    continue
                if not isinstance(data, dict):
                    raise ValueError('Expected mapping')
                if '/workflows/' in rel:
                    if not isinstance(data.get('jobs'), dict) or not data['jobs'] or not data.get('on'):
                        raise ValueError('Workflow needs events and jobs')
                    if data.get('permissions') != {'contents': 'read'}:
                        raise ValueError('Workflow must grant only contents: read')
                    if 'pull_request_target' in data['on']:
                        raise ValueError('Privileged pull request event unsupported')
                    for job in data['jobs'].values():
                        if not job.get('runs-on') or not job.get('timeout-minutes') or not job.get('steps'):
                            raise ValueError('Job needs runner, timeout and steps')
                        for step in job['steps']:
                            if not isinstance(step, dict) or not (step.get('run') or step.get('uses')):
                                raise ValueError('Step needs run or uses')
                            uses = str(step.get('uses', ''))
                            if uses and not uses.startswith('./') and '@' not in uses:
                                raise ValueError('External action needs ref')
                            if uses.startswith('actions/checkout@') and str(
                                    step.get('with', {}).get('persist-credentials')).lower() != 'false':
                                raise ValueError('Checkout must disable credential persistence')
                elif 'dependabot' in rel:
                    if str(data.get('version')) != '2' or not data.get('updates'):
                        raise ValueError('Dependabot needs version 2 and updates')
                    seen = set()
                    for item in data['updates']:
                        key = (item.get('package-ecosystem'), item.get('directory'))
                        if key in seen or not key[0] or not str(key[1]).startswith('/'):
                            raise ValueError('Invalid or duplicate Dependabot update')
                        if item.get('schedule', {}).get('interval') not in {'daily', 'weekly', 'monthly'}:
                            raise ValueError('Invalid Dependabot schedule')
                        seen.add(key)
                elif '/ISSUE_TEMPLATE/' in rel:
                    if p.stem == 'config':
                        if str(data.get('blank_issues_enabled')).lower() not in {'true', 'false'}:
                            raise ValueError('Issue config needs blank_issues_enabled')
                    else:
                        if not data.get('name') or not data.get('description') or not data.get('body'):
                            raise ValueError('Issue form needs name, description, body')
                        ids = set()
                        for field in data['body']:
                            if field.get('type') not in {'markdown', 'textarea', 'input', 'dropdown', 'checkboxes'}:
                                raise ValueError('Unsupported issue field')
                            if field['type'] != 'markdown':
                                if not field.get('id') or field['id'] in ids or not field.get('attributes', {}).get('label'):
                                    raise ValueError('Issue field needs unique id and label')
                                ids.add(field['id'])
            elif rel == '.editorconfig':
                config = configparser.ConfigParser(interpolation=None, strict=True)
                config.read_string('[DEFAULT]\n' + body)
                if config.defaults().get('root') != 'true' or '*' not in config:
                    raise ValueError('EditorConfig needs root=true and [*]')
            elif rel.endswith('PULL_REQUEST_TEMPLATE.md'):
                for heading in ('Summary', 'Changes', 'Testing', 'Breaking Changes', 'Risks', 'Checklist'):
                    if f'## {heading}' not in body:
                        raise ValueError('Missing PR section: ' + heading)
            checked.append(rel)
        except Exception as exc:
            # Do not echo parser excerpts that could contain credentials.
            errors.append(f'{rel}: structural validation failed ({type(exc).__name__})')
    return {'status': 'failed' if errors else 'partial' if unverified else 'passed',
            'checked': checked, 'errors': errors, 'unverified': unverified,
            'scope': 'Structural checks only; no application builds or GitHub execution'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.root.resolve())
        print(json.dumps(result, indent=2))
        sys.exit(0 if result['status'] == 'passed' else 1)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Configuration validation failed ({type(exc).__name__})\n')
