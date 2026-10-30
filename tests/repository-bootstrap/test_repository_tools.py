"""Repository tooling checks use synthetic skills and temporary files only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'skills/workflow/delivery/repository-bootstrap/scripts'))
import install_skill
import validate_skills
from validate_configuration import validate


class RepositoryToolsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='skill-tools-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.skill = self.root / 'skills/example'
        self.skill.mkdir(parents=True)
        self.catalog({'schema_version': 1, 'skills': {'example': 'skills/example'}})
        # JSON frontmatter is also valid YAML, allowing offline metadata tests.
        self.metadata({'name': 'example', 'description': 'A synthetic test skill.'})

    def catalog(self, data):
        (self.root / 'skills.json').write_text(json.dumps(data), encoding='utf-8')

    def metadata(self, data):
        (self.skill / 'SKILL.md').write_text('---\n' + json.dumps(data) + '\n---\n# Example\n', encoding='utf-8')

    def test_generic_skill_needs_no_bootstrap_scripts(self):
        self.assertEqual(validate_skills.validate_repository(self.root)['status'], 'passed')

    def test_metadata_type_errors_are_reported(self):
        for value in (None, [], 'invalid', {'version': 1}):
            with self.subTest(value=value):
                self.metadata({'name': 'example', 'description': 'Example', 'metadata': value})
                self.assertEqual(validate_skills.validate_repository(self.root)['status'], 'failed')

    def test_missing_yaml_does_not_skip_other_checks(self):
        (self.skill / 'SKILL.md').write_text('---\nname: example\ndescription: Example\n---\n', encoding='utf-8')
        (self.skill / 'broken.py').write_text('invalid python source!', encoding='utf-8')
        with patch.object(validate_skills, 'yaml', None):
            report = validate_skills.validate_repository(self.root)
        self.assertEqual(report['status'], 'failed')
        self.assertTrue(report['unverified'])
        self.assertTrue(any('broken.py' in error for error in report['errors']))

    def test_missing_yaml_reports_partial(self):
        (self.skill / 'SKILL.md').write_text('---\nname: example\ndescription: Example\n---\n', encoding='utf-8')
        with patch.object(validate_skills, 'yaml', None):
            report = validate_skills.validate_repository(self.root)
        self.assertEqual(report['status'], 'partial')
        self.assertFalse(report['errors'])

    def test_links_in_references_are_checked(self):
        references = self.skill / 'references'
        references.mkdir()
        (references / 'guide.md').write_text('[broken](missing.md)', encoding='utf-8')
        report = validate_skills.validate_repository(self.root)
        self.assertEqual(report['status'], 'failed')
        self.assertTrue(any('guide.md' in error for error in report['errors']))

    def test_relative_parent_link_inside_skill_is_valid(self):
        references = self.skill / 'references'
        references.mkdir()
        (references / 'guide.md').write_text('[home](../SKILL.md)', encoding='utf-8')
        self.assertEqual(validate_skills.validate_repository(self.root)['status'], 'passed')

    def test_links_cannot_escape_skill(self):
        (self.root / 'outside.md').write_text('outside', encoding='utf-8')
        with (self.skill / 'SKILL.md').open('a', encoding='utf-8') as stream:
            stream.write('[outside](../../outside.md)')
        self.assertEqual(validate_skills.validate_repository(self.root)['status'], 'failed')

    def test_duplicate_catalog_keys_are_rejected(self):
        (self.root / 'skills.json').write_text('{"schema_version":1,"skills":{},"skills":{}}', encoding='utf-8')
        self.assertEqual(validate_skills.validate_repository(self.root)['status'], 'failed')

    def test_malformed_catalog_does_not_disclose_contents(self):
        (self.root / 'skills.json').write_text('secret-token-invalid-json', encoding='utf-8')
        report = validate_skills.validate_repository(self.root)
        self.assertEqual(report['status'], 'failed')
        self.assertNotIn('secret-token', json.dumps(report))

    def test_catalog_cannot_escape_skills(self):
        self.catalog({'schema_version': 1, 'skills': {'example': '../example'}})
        self.assertEqual(validate_skills.validate_repository(self.root)['status'], 'failed')
        with patch.object(install_skill, '__file__', str(self.root / 'scripts/install_skill.py')):
            with self.assertRaises(ValueError):
                install_skill.install('example', self.root / 'destination')
        self.assertFalse((self.root / 'destination').exists())

    def test_inspected_python_is_not_executed(self):
        marker = self.root / 'executed'
        (self.skill / 'dangerous.py').write_text(
            'from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()\n', encoding='utf-8')
        self.assertEqual(validate_skills.validate_repository(self.root)['status'], 'passed')
        self.assertFalse(marker.exists())

    def test_real_repository_automation_is_structurally_valid(self):
        result = validate(ROOT, paths=['.github/workflows/validate-skills.yml', '.github/dependabot.yml'])
        self.assertEqual(result['status'], 'passed', result)

    @unittest.skipUnless(os.name == 'nt', 'Windows junction regression')
    def test_installer_and_validator_reject_linked_resources(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'private.txt').write_text('private-data', encoding='utf-8')
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(self.skill / 'assets'), str(outside)],
                                capture_output=True, check=False)
        if result.returncode:
            self.skipTest('Creating junctions is unavailable')
        self.assertEqual(validate_skills.validate_repository(self.root)['status'], 'failed')
        with patch.object(install_skill, '__file__', str(self.root / 'scripts/install_skill.py')):
            with self.assertRaises(ValueError):
                install_skill.install('example', self.root / 'destination')
        self.assertFalse((self.root / 'destination').exists())


if __name__ == '__main__':
    unittest.main()
