"""Conservative offline repository infrastructure planner and applier (Python 3.10+)."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET

ASSETS = Path(__file__).resolve().parent.parent / 'assets'
EXCLUDED = {'.git', '.hg', '.svn', 'target', 'build', 'vendor', 'node_modules',
            '.venv', 'venv', '.gradle', '__pycache__', '.idea'}


def linked(path):
    # Path.is_junction is unavailable on Python 3.10/3.11. Reject all Windows
    # reparse points, including junctions, without following their targets.
    try:
        attributes = getattr(path.lstat(), 'st_file_attributes', 0)
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def safe_path(root, relative):
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Unsafe relative path')
    current = root
    for part in rel.parts:
        current = current / part
        if linked(current):
            raise ValueError('Linked paths require manual review')
        if current != root / rel and current.exists() and not current.is_dir():
            raise ValueError('Parent is not a directory')
    if not (root / rel).resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes target')
    return root / rel


def read(path):
    if path.stat().st_size > 1_000_000:
        raise ValueError('Configuration exceeds 1 MB inspection limit')
    return path.read_text(encoding='utf-8-sig')


def git_result(root, *args):
    try:
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                                text=True, timeout=10, check=False)
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ''


def inspect(root):
    root = root.resolve()
    if not root.is_dir():
        raise ValueError('Target must be a directory')
    rc, top = git_result(root, 'rev-parse', '--show-toplevel')
    initialized = rc == 0 and Path(top).resolve() == root
    result = {'git': {'initialized': initialized,
                      'has_commits': bool(initialized and git_result(root, 'rev-parse', '--verify', 'HEAD')[0] == 0),
                      'inside_parent_repository': rc == 0 and not initialized,
                      'git_available': rc != 127},
              'projects': [], 'existing_configuration': [], 'warnings': []}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not linked(Path(directory, d))
                         and not Path(directory, d, '.git').exists())
        for name in sorted(files):
            if name not in {'pom.xml', 'build.gradle', 'build.gradle.kts', 'go.mod'}:
                continue
            p = Path(directory, name)
            rel = p.relative_to(root).as_posix()
            try:
                safe_path(root, rel)
                body = read(p)
                kind = 'maven' if name == 'pom.xml' else 'go' if name == 'go.mod' else 'gradle'
                version = None
                if kind == 'maven':
                    if '<!DOCTYPE' in body.upper() or '<!ENTITY' in body.upper():
                        raise ValueError('XML entities/DOCTYPE are not inspected')
                    tree = ET.fromstring(body)
                    props = next((e for e in tree if e.tag.split('}')[-1] == 'properties'), [])
                    values = {e.tag.split('}')[-1]: (e.text or '').strip() for e in props}
                    versions = {values[k] for k in ('maven.compiler.release', 'java.version',
                                'maven.compiler.source', 'maven.compiler.target') if k in values}
                    versions = {v[2:] if v.startswith('1.') else v for v in versions}
                    if len(versions) == 1:
                        candidate = versions.pop()
                        if re.fullmatch(r'[1-9][0-9]*', candidate):
                            version = candidate
                elif kind == 'gradle':
                    body = re.sub(r'/\*.*?\*/|//[^\n]*', '', body, flags=re.S)
                    matches = set(re.findall(r'JavaLanguageVersion\.of\(\s*([1-9][0-9]*)\s*\)', body))
                    if len(matches) == 1:
                        version = matches.pop()
                else:
                    match = re.search(r'^go\s+(1\.[0-9]+(?:\.[0-9]+)?)\s*(?://.*)?$', body, re.M)
                    if match:
                        version = match.group(1)
                result['projects'].append({'type': kind, 'manifest': rel,
                    'directory': p.parent.relative_to(root).as_posix(), 'version': version})
            except (OSError, ValueError, ET.ParseError) as exc:
                result['warnings'].append(f'{rel}: inspection failed ({type(exc).__name__})')
    for rel in ['README.md', 'AGENTS.md', '.gitignore', '.editorconfig']:
        if (root / rel).exists() or linked(root / rel):
            result['existing_configuration'].append(rel)
    try:
        safe_path(root, '.github')
        for directory, dirs, files in os.walk(root / '.github', followlinks=False):
            dirs[:] = sorted(d for d in dirs if not linked(Path(directory, d)))
            result['existing_configuration'].extend(
                Path(directory, f).relative_to(root).as_posix() for f in sorted(files))
    except ValueError:
        result['warnings'].append('.github: linked configuration requires manual review')
    if not result['projects']:
        result['warnings'].append('Unknown project type; no application commands inferred')
    result['existing_configuration'] = sorted(set(result['existing_configuration']))
    return result


def dump(data):
    # JSON is a YAML 1.2 subset accepted by GitHub; no YAML runtime dependency.
    return json.dumps(data, indent=2, ensure_ascii=True) + '\n'


def workflow(jobs):
    return {'name': 'CI', 'on': {'push': {}, 'pull_request': {}},
            'permissions': {'contents': 'read'},
            'concurrency': {'group': '${{ github.workflow }}-${{ github.ref }}',
                            'cancel-in-progress': True}, 'jobs': jobs}


def proposals(root, info, java_version=None, java_distribution=None):
    files, skips = {}, []
    for source, dest in [('README.template.md', 'README.md'), ('AGENTS.template.md', 'AGENTS.md'),
                         ('editorconfig.template', '.editorconfig'),
                         ('PULL_REQUEST_TEMPLATE.md', '.github/PULL_REQUEST_TEMPLATE.md'),
                         ('bug_report.yml', '.github/ISSUE_TEMPLATE/bug_report.yml'),
                         ('feature_request.yml', '.github/ISSUE_TEMPLATE/feature_request.yml'),
                         ('config.yml', '.github/ISSUE_TEMPLATE/config.yml')]:
        files[dest] = read(ASSETS / source)
    kinds = {p['type'] for p in info['projects']}
    fragments = ['common'] + (['java'] if kinds & {'maven', 'gradle'} else []) + (['go'] if 'go' in kinds else [])
    files['.gitignore'] = ''.join(read(ASSETS / f'gitignore-{part}.txt') for part in fragments)
    jobs = {}
    updates = [{'package-ecosystem': 'github-actions', 'directory': '/', 'schedule': {'interval': 'weekly'}}]
    for index, project in enumerate(info['projects']):
        kind, directory = project['type'], project['directory']
        # GitHub interprets expressions even in JSON strings; never interpolate paths.
        if '${{' in directory or any(ord(c) < 32 for c in directory):
            skips.append(f"{project['manifest']}: unsafe CI directory requires manual configuration")
            continue
        update = {'package-ecosystem': 'gomod' if kind == 'go' else kind,
                  'directory': '/' if directory == '.' else '/' + directory,
                  'schedule': {'interval': 'weekly'}}
        if update not in updates:
            updates.append(update)
        version = project['version'] if kind == 'go' else java_version or project['version']
        steps = [{'uses': 'actions/checkout@v7', 'with': {'persist-credentials': False}}]
        if kind == 'go':
            if not version:
                skips.append(f"{project['manifest']}: missing literal Go version")
                continue
            steps.append({'uses': 'actions/setup-go@v7', 'with': {
                'go-version-file': project['manifest'], 'cache': False}})
            command = 'go test ./...'
        else:
            if not version or not java_distribution:
                skips.append(f"{project['manifest']}: Java CI requires known JDK and explicit --java-distribution")
                continue
            base = Path(directory) if directory != '.' else Path()
            required = [base / ('mvnw' if kind == 'maven' else 'gradlew'),
                        base / ('.mvn/wrapper/maven-wrapper.properties' if kind == 'maven'
                                else 'gradle/wrapper/gradle-wrapper.properties')]
            if kind == 'gradle':
                required.append(base / 'gradle/wrapper/gradle-wrapper.jar')
            try:
                complete = all(safe_path(root, p.as_posix()).is_file() for p in required)
            except ValueError:
                complete = False
            if not complete:
                skips.append(f"{project['manifest']}: complete local {kind} wrapper required")
                continue
            steps.append({'uses': 'actions/setup-java@v6', 'with': {
                'distribution': java_distribution, 'java-version': version}})
            command = 'bash ./mvnw --batch-mode verify' if kind == 'maven' else 'bash ./gradlew build --no-daemon'
        steps.append({'run': command})
        jobs[f'{kind}-{index}'] = {'runs-on': 'ubuntu-latest', 'timeout-minutes': 20,
                                  'defaults': {'run': {'working-directory': directory}}, 'steps': steps}
    files['.github/dependabot.yml'] = dump({'version': 2, 'updates': updates})
    if jobs:
        files['.github/workflows/ci.yml'] = dump(workflow(jobs))
    else:
        skips.append('.github/workflows/ci.yml: insufficient evidence for runnable application CI')
    return files, skips


def digest(data):
    return hashlib.sha256(data).hexdigest()


def plan(root, java_version=None, java_distribution=None):
    root = root.resolve()
    info = inspect(root)
    desired, skips = proposals(root, info, java_version, java_distribution)
    operations = []
    for rel, content in sorted(desired.items()):
        op = {'path': rel, 'action': 'CREATE', 'reason': 'Missing standard-profile file',
              'before_sha256': None, 'content': content}
        try:
            path = safe_path(root, rel)
            if path.exists():
                if not path.is_file():
                    raise ValueError('Target is not a regular file')
                if path.stat().st_size > 1_000_000:
                    raise ValueError('Configuration exceeds 1 MB inspection limit')
                old = path.read_bytes()
                op['before_sha256'] = digest(old)
                if old == content.encode():
                    op.update(action='PRESERVE', reason='Already matches proposed content')
                elif rel == '.gitignore':
                    read(path)  # Enforce the configuration size and encoding limits.
                    existing = old.decode('utf-8')  # Retain BOM and original line endings.
                    newline = '\r\n' if '\r\n' in existing else '\n'
                    if any(line.strip().startswith('!') for line in existing.splitlines()):
                        op.update(action='CONFLICT', reason='Ignore negation rules require semantic review')
                    else:
                        missing = [line for line in content.splitlines() if line and not line.startswith('#')
                                   and line not in existing.splitlines()]
                        if missing:
                            op.update(action='MERGE', reason='Append missing additive ignore rules',
                                      content=existing + ('' if existing.endswith('\n') else newline)
                                      + newline + '# repository-bootstrap additions' + newline
                                      + newline.join(missing) + newline)
                        else:
                            op.update(action='PRESERVE', reason='Ignore rules already present')
                elif rel.endswith(('.yml', '.yaml')):
                    op.update(action='CONFLICT', reason='Existing structured configuration differs; manual merge required')
                else:
                    op.update(action='PRESERVE', reason='Preserve existing documentation and conventions')
            elif rel == 'README.md' and any(p.is_file() and p.name.lower().startswith('readme')
                                             for p in root.iterdir()):
                op.update(action='CONFLICT', reason='Alternate README exists; preserve documentation convention')
            elif rel == '.github/PULL_REQUEST_TEMPLATE.md' and any(
                    'pull_request_template' in p.lower() for p in info['existing_configuration']):
                op.update(action='CONFLICT', reason='Alternate pull request template exists')
            elif rel == '.github/workflows/ci.yml' and any(
                    p.startswith('.github/workflows/') and p.endswith(('.yml', '.yaml'))
                    for p in info['existing_configuration']):
                op.update(action='CONFLICT', reason='Another workflow exists; inspect for duplicate CI')
            elif rel == '.github/dependabot.yml' and (root / '.github/dependabot.yaml').exists():
                op.update(action='CONFLICT', reason='Alternate Dependabot configuration exists')
        except (OSError, ValueError) as exc:
            op.update(action='CONFLICT', reason=f'Unsafe or unreadable target ({type(exc).__name__})')
        operations.append(op)
    operations.extend({'path': s.split(':', 1)[0], 'action': 'SKIP', 'reason': s,
                       'before_sha256': None} for s in skips)
    return {'profile': 'standard', 'inspection': info, 'operations': operations,
            'assumptions': ['Commands are build-system defaults; application builds were not executed.',
                            'GitHub settings are recommendations only.'],
            'applied': [], 'validation': {'status': 'not-run'}}


def apply(root, report):
    """Preflight all writes; CREATE is exclusive. Not a concurrent-writer transaction."""
    changes = [op for op in report['operations'] if op['action'] in {'CREATE', 'MERGE'}]
    for op in changes:
        path = safe_path(root, op['path'])
        current = digest(path.read_bytes()) if path.is_file() else None
        if current != op['before_sha256'] or (path.exists() and not path.is_file()):
            raise ValueError(f"Target changed after planning: {op['path']}")
    for op in changes:
        path = safe_path(root, op['path'])
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = 'x' if op['action'] == 'CREATE' else 'w'
        with path.open(mode, encoding='utf-8', newline='\n') as stream:
            stream.write(op['content'])
        report['applied'].append(op['path'])
    from validate_configuration import validate
    eligible = report['applied'] + [op['path'] for op in report['operations']
        if op['action'] == 'PRESERVE' and op['reason'] == 'Already matches proposed content']
    report['validation'] = validate(root, paths=eligible)
    report['validation']['scope'] = 'Changed or identical generated files only; custom preserved/conflicting files and application builds unverified'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--java-version', help='Explicit user-selected JDK override')
    parser.add_argument('--java-distribution', choices=['temurin', 'zulu', 'corretto', 'microsoft', 'oracle'])
    parser.add_argument('--include-content', action='store_true', help='Show proposed CREATE content only')
    args = parser.parse_args()
    if args.java_version and not re.fullmatch(r'[1-9][0-9]*(?:\.[0-9]+)*', args.java_version):
        parser.error('--java-version must be numeric')
    try:
        root = args.root.resolve()
        report = plan(root, args.java_version, args.java_distribution)
        if args.apply:
            apply(root, report)
        public = {**report, 'operations': [{k: v for k, v in op.items() if k != 'content'
                  or (args.include_content and op['action'] == 'CREATE')} for op in report['operations']]}
        print(dump(public), end='')
        return 1 if report['validation']['status'] == 'failed' else 2 if any(
            o['action'] == 'CONFLICT' for o in report['operations']) else 0
    except (OSError, ValueError) as exc:
        print(f'Bootstrap failed ({type(exc).__name__}): {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
