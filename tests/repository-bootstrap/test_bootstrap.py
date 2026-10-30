"""Offline behavioral fixtures; all writes are confined to temporary directories."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'skills/workflow/delivery/repository-bootstrap/scripts'
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / 'scripts'))
from bootstrap import apply, inspect, plan, safe_path
from check_idempotency import check, snapshot
from validate_configuration import validate, parse_yaml
from install_skill import install


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bootstrap-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'
        self.root.mkdir()

    def write(self, relative, content):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return target

    def git(self, *args):
        if not shutil.which('git'):
            self.skipTest('Git not installed')
        subprocess.run(['git', '-C', str(self.root), *args], check=True,
                       capture_output=True, env={**{k: v for k, v in os.environ.items() if not k.startswith('GIT_')},
                           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull})

    def go(self, directory=''):
        prefix = directory + '/' if directory else ''
        self.write(prefix + 'go.mod', 'module example.invalid/test\n\ngo 1.23.0\n')

    def maven(self, directory='', version='21'):
        prefix = directory + '/' if directory else ''
        self.write(prefix + 'pom.xml', '<project><properties><maven.compiler.release>' + version
                   + '</maven.compiler.release></properties></project>')
        self.write(prefix + 'mvnw', '#!/bin/sh\n# Synthetic fixture: never executed\n')
        self.write(prefix + '.mvn/wrapper/maven-wrapper.properties',
                   'distributionUrl=https://example.invalid/apache-maven.zip\n')

    def gradle(self):
        self.write('build.gradle.kts', 'java { toolchain { languageVersion.set(JavaLanguageVersion.of(21)) } }')
        self.write('gradlew', '#!/bin/sh\n# Synthetic fixture: never executed\n')
        self.write('gradle/wrapper/gradle-wrapper.properties', 'distributionUrl=https://example.invalid/gradle.zip\n')
        self.write('gradle/wrapper/gradle-wrapper.jar', 'synthetic detection fixture, not executed')

    def run_bootstrap(self, **options):
        report = apply(self.root, plan(self.root, **options))
        self.assertEqual(report['validation']['status'], 'passed', report['validation'])
        return report

    def ci(self):
        return json.loads((self.root / '.github/workflows/ci.yml').read_text())

    def test_empty_directory(self):
        report = self.run_bootstrap()
        self.assertFalse(report['inspection']['git']['initialized'])
        self.assertTrue((self.root / 'AGENTS.md').is_file())
        self.assertFalse((self.root / '.github/workflows/ci.yml').exists())
        self.assertTrue(any(o['action'] == 'SKIP' for o in report['operations']))
        self.assertFalse((self.root / '.git').exists())

    def test_empty_git_repository(self):
        self.git('init')
        before = snapshot(self.root / '.git')
        report = self.run_bootstrap()
        self.assertTrue(report['inspection']['git']['initialized'])
        self.assertFalse(report['inspection']['git']['has_commits'])
        self.assertEqual(before, snapshot(self.root / '.git'))

    def test_repository_with_commit(self):
        self.git('init')
        self.write('existing.txt', 'keep me')
        self.git('add', 'existing.txt')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '--no-gpg-sign', '-m', 'fixture')
        before = (self.root / '.git/HEAD').read_bytes()
        report = self.run_bootstrap()
        self.assertTrue(report['inspection']['git']['has_commits'])
        self.assertEqual(before, (self.root / '.git/HEAD').read_bytes())
        self.assertEqual((self.root / 'existing.txt').read_text(), 'keep me')

    def test_maven(self):
        self.maven()
        self.run_bootstrap(java_distribution='temurin')
        job = next(iter(self.ci()['jobs'].values()))
        self.assertEqual(job['steps'][1]['with']['java-version'], '21')
        self.assertEqual(job['steps'][-1]['run'], 'bash ./mvnw --batch-mode verify')
        self.assertIn('**/target/', (self.root / '.gitignore').read_text())

    def test_gradle(self):
        self.gradle()
        self.run_bootstrap(java_distribution='zulu')
        job = next(iter(self.ci()['jobs'].values()))
        self.assertEqual(job['steps'][1]['with']['distribution'], 'zulu')
        self.assertEqual(job['steps'][-1]['run'], 'bash ./gradlew build --no-daemon')

    def test_go_modules(self):
        self.go()
        self.run_bootstrap()
        job = next(iter(self.ci()['jobs'].values()))
        self.assertEqual(job['steps'][1]['with']['go-version-file'], 'go.mod')
        self.assertFalse(job['steps'][1]['with']['cache'])
        self.assertNotIn('go.sum', (self.root / '.gitignore').read_text().splitlines())

    def test_mixed_monorepository(self):
        self.maven('java-service')
        self.go('go-service')
        self.run_bootstrap(java_distribution='temurin')
        dirs = {j['defaults']['run']['working-directory'] for j in self.ci()['jobs'].values()}
        self.assertEqual(dirs, {'java-service', 'go-service'})
        updates = json.loads((self.root / '.github/dependabot.yml').read_text())['updates']
        self.assertEqual({u['package-ecosystem'] for u in updates}, {'github-actions', 'maven', 'gomod'})

    def test_existing_custom_configuration_preserved(self):
        values = {'README.md': b'# Custom\r\n', 'AGENTS.md': b'Project conventions\r\n',
                  '.editorconfig': b'root = true\r\n[*]\r\nindent_size = 8\r\n',
                  '.github/dependabot.yml': b'version: 2\nupdates: []\n',
                  '.github/ISSUE_TEMPLATE/config.yml': b'blank_issues_enabled: true\n'}
        for relative, content in values.items():
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.write('business.go', 'unchanged application source')
        self.run_bootstrap()
        for relative, content in values.items():
            self.assertEqual((self.root / relative).read_bytes(), content)
        self.assertEqual((self.root / 'business.go').read_text(), 'unchanged application source')

    def test_repeated_execution_is_idempotent(self):
        self.maven()
        self.go('other')
        self.run_bootstrap(java_distribution='temurin')
        before = snapshot(self.root)
        report = self.run_bootstrap(java_distribution='temurin')
        self.assertFalse(report['applied'])
        self.assertEqual(before, snapshot(self.root))

    def test_conflicting_ci_workflow(self):
        self.go()
        body = 'name: Custom\non: push\njobs: {}\n'
        self.write('.github/workflows/ci.yml', body)
        report = self.run_bootstrap()
        op = next(o for o in report['operations'] if o['path'] == '.github/workflows/ci.yml')
        self.assertEqual(op['action'], 'CONFLICT')
        self.assertEqual((self.root / '.github/workflows/ci.yml').read_text(), body)

    def test_other_workflow_prevents_duplicate_ci(self):
        self.go()
        self.write('.github/workflows/build.yaml', 'name: Existing\n')
        report = self.run_bootstrap()
        self.assertFalse((self.root / '.github/workflows/ci.yml').exists())
        self.assertTrue(any(o['action'] == 'CONFLICT' for o in report['operations']))

    def test_ignore_merge_preserves_lines_and_is_stable(self):
        self.write('.gitignore', 'custom-output/\n')
        first = self.run_bootstrap()
        self.assertTrue(any(o['action'] == 'MERGE' for o in first['operations']))
        self.assertTrue((self.root / '.gitignore').read_text().startswith('custom-output/\n'))
        self.assertFalse(self.run_bootstrap()['applied'])

    def test_ignore_negations_require_review(self):
        self.write('.gitignore', '*.env\n!example.env\n')
        report = self.run_bootstrap()
        self.assertEqual((self.root / '.gitignore').read_text(), '*.env\n!example.env\n')
        self.assertTrue(any(o['path'] == '.gitignore' and o['action'] == 'CONFLICT' for o in report['operations']))

    def test_missing_java_version_and_wrapper_not_invented(self):
        self.write('pom.xml', '<project/>')
        report = self.run_bootstrap(java_distribution='temurin')
        self.assertFalse((self.root / '.github/workflows/ci.yml').exists())
        self.assertFalse((self.root / 'mvnw').exists())
        self.assertTrue(any('JDK' in o['reason'] for o in report['operations']))

    def test_java_distribution_not_invented(self):
        self.maven()
        self.run_bootstrap()
        self.assertFalse((self.root / '.github/workflows/ci.yml').exists())

    def test_nested_go_modules_each_get_job(self):
        self.go()
        self.go('nested')
        self.run_bootstrap()
        self.assertEqual(len(self.ci()['jobs']), 2)

    def test_unknown_type_has_no_guessed_build(self):
        self.write('package.json', '{"name":"unknown-stack"}')
        self.run_bootstrap()
        self.assertFalse((self.root / '.github/workflows/ci.yml').exists())
        self.assertNotIn('node_modules', (self.root / '.gitignore').read_text())

    def test_dry_run_does_not_write(self):
        self.go()
        before = snapshot(self.root)
        report = plan(self.root)
        self.assertEqual(before, snapshot(self.root))
        self.assertEqual(report['validation']['status'], 'not-run')

    def test_stale_plan_aborts_before_any_writes(self):
        report = plan(self.root)
        self.write('README.md', 'arrived after planning')
        with self.assertRaises(ValueError):
            apply(self.root, report)
        self.assertFalse((self.root / '.github').exists())
        self.assertEqual((self.root / 'README.md').read_text(), 'arrived after planning')

    def test_parent_file_blocks_configuration(self):
        self.write('.github', 'a regular file')
        report = self.run_bootstrap()
        self.assertTrue(any(o['action'] == 'CONFLICT' for o in report['operations']))
        self.assertEqual((self.root / '.github').read_text(), 'a regular file')

    def test_symlink_is_never_modified(self):
        other = self.base / 'outside'
        other.mkdir()
        try:
            (self.root / '.github').symlink_to(other, target_is_directory=True)
        except OSError:
            self.skipTest('Creating symlinks is not available for this user')
        report = self.run_bootstrap()
        self.assertFalse(list(other.iterdir()))
        self.assertTrue(any(o['action'] == 'CONFLICT' for o in report['operations']))

    def test_escaping_path_rejected(self):
        with self.assertRaises(ValueError):
            safe_path(self.root, '../outside')

    def test_malformed_manifest_does_not_disclose_contents(self):
        self.write('pom.xml', '<project>secret-credential-123')
        facts = inspect(self.root)
        self.assertTrue(facts['warnings'])
        self.assertNotIn('secret-credential-123', json.dumps(facts))

    def test_invalid_generated_workflow_is_detected(self):
        self.go()
        self.run_bootstrap()
        ci = self.ci()
        ci['permissions'] = {'contents': 'write'}
        self.write('.github/workflows/ci.yml', json.dumps(ci))
        self.assertEqual(validate(self.root)['status'], 'failed')

    def test_idempotency_checker_never_modifies_source(self):
        self.go()
        before = snapshot(self.root)
        result = check(self.root)
        self.assertTrue(result['idempotent'])
        self.assertEqual(before, snapshot(self.root))

    def test_install_flat_and_refuse_overwrite(self):
        target = install('repository-bootstrap', self.base / 'discovery')
        self.assertTrue((target / 'SKILL.md').is_file())
        self.assertTrue((target / 'assets/bug_report.yml').is_file())
        self.assertTrue((target / 'scripts/bootstrap.py').is_file())
        with self.assertRaises(ValueError):
            install('repository-bootstrap', self.base / 'discovery')
        with self.assertRaises(ValueError):
            install('requirements-analysis', self.base / 'discovery')

    def test_installed_skill_runs_standalone(self):
        target = install('repository-bootstrap', self.base / 'discovery')
        result = subprocess.run([sys.executable, '-B', str(target / 'scripts/bootstrap.py'), str(self.root), '--apply'],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['validation']['status'], 'passed')

    def test_cli_conflicts_return_exit_two_without_secret_output(self):
        self.write('.github/dependabot.yml', 'secret-token-123')
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'bootstrap.py'), str(self.root),
                                 '--apply', '--include-content'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('secret-token-123', result.stdout + result.stderr)
        self.assertTrue((self.root / 'README.md').exists())

    def test_missing_git_does_not_prevent_bootstrap(self):
        with patch('bootstrap.git_result', return_value=(127, '')):
            report = self.run_bootstrap()
        self.assertFalse(report['inspection']['git']['git_available'])

    def test_yaml_parser_rejects_duplicate_keys(self):
        try:
            import yaml
        except ImportError:
            self.skipTest('PyYAML is optional for ordinary YAML')
        with self.assertRaises(ValueError):
            parse_yaml('name: first\nname: second\n')


    def test_expression_directory_does_not_enter_workflow(self):
        # Braces and dollars are legal filenames on supported operating systems.
        self.go('unsafe-${{ secrets.TOKEN }}')
        report = self.run_bootstrap()
        self.assertFalse((self.root / '.github/workflows/ci.yml').exists())
        self.assertTrue(any('unsafe CI directory' in o['reason'] for o in report['operations']))

    def test_gradle_comment_does_not_invent_jdk(self):
        self.gradle()
        self.write('build.gradle.kts', '// JavaLanguageVersion.of(99)\nplugins { java }')
        self.run_bootstrap(java_distribution='temurin')
        self.assertFalse((self.root / '.github/workflows/ci.yml').exists())

    def test_alternate_readme_convention_is_preserved(self):
        self.write('README.rst', 'Custom documentation')
        report = self.run_bootstrap()
        self.assertFalse((self.root / 'README.md').exists())
        self.assertTrue(any(o['path'] == 'README.md' and o['action'] == 'CONFLICT' for o in report['operations']))

    def test_missing_wrapper_requires_manual_followup(self):
        self.maven()
        (self.root / 'mvnw').unlink()
        report = self.run_bootstrap(java_distribution='temurin')
        self.assertFalse((self.root / '.github/workflows/ci.yml').exists())
        self.assertTrue(any('wrapper required' in o['reason'] for o in report['operations']))

    def test_nested_independent_java_builds_are_not_silently_skipped(self):
        self.maven()
        self.maven('independent')
        self.run_bootstrap(java_distribution='temurin')
        self.assertEqual(len(self.ci()['jobs']), 2)

    def test_json_duplicate_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_yaml('{"name":"first","name":"second"}')

    def test_repeat_validation_checks_actual_generated_files(self):
        self.go()
        self.run_bootstrap()
        report = self.run_bootstrap()
        self.assertFalse(report['applied'])
        self.assertIn('.github/workflows/ci.yml', report['validation']['checked'])

    def test_ignore_merge_keeps_original_bytes_and_line_endings(self):
        original = b'\xef\xbb\xbfcustom-output/\r\nlogs/\r\n'
        (self.root / '.gitignore').write_bytes(original)
        self.run_bootstrap()
        result = (self.root / '.gitignore').read_bytes()
        self.assertTrue(result.startswith(original))
        self.assertIn(b'# repository-bootstrap additions\r\n', result)
        self.assertFalse(self.run_bootstrap()['applied'])

    def test_oversized_configuration_is_preserved_as_conflict(self):
        original = b'x' * 1_000_001
        (self.root / 'README.md').write_bytes(original)
        report = self.run_bootstrap()
        self.assertEqual((self.root / 'README.md').read_bytes(), original)
        self.assertTrue(any(o['path'] == 'README.md' and o['action'] == 'CONFLICT'
                            for o in report['operations']))

    def test_idempotency_copy_excludes_nested_repositories(self):
        self.go('independent')
        self.write('independent/.git', 'gitdir: synthetic-worktree')
        result = check(self.root)
        self.assertTrue(result['idempotent'])
        self.assertNotIn('.github/workflows/ci.yml', result['first_applied'])

    def test_validation_cli_missing_target_fails_without_traceback(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'validate_configuration.py'),
                                 str(self.base / 'missing')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('Traceback', result.stdout + result.stderr)

    @unittest.skipUnless(os.name == 'nt', 'Windows junction regression')
    def test_junction_is_preserved_and_idempotency_retains_conflicts(self):
        outside = self.base / 'outside'
        outside.mkdir()
        link = self.root / '.github'
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)],
                                capture_output=True, check=False)
        if result.returncode:
            self.skipTest('Creating junctions is unavailable')
        report = self.run_bootstrap()
        self.assertTrue(any(o['action'] == 'CONFLICT' for o in report['operations']))
        result = check(self.root)
        self.assertTrue(result['conflicts'])
        self.assertFalse(list(outside.iterdir()))


if __name__ == '__main__':
    unittest.main()
