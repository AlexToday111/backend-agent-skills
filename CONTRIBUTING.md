# Contributing

Use Python 3.10+ and Git. Installed runtime scripts are dependency-free. Full validation
additionally uses python -m pip install -r requirements-validation.txt (PyYAML 6.0.3).
A virtual environment is recommended. No test requires GitHub credentials or network.

Run python scripts/validate_skills.py and
python -m unittest discover -s tests/repository-bootstrap -v from the root.
CI runs both on Python 3.10/3.13 and Ubuntu/Windows. Templates are JSON-form YAML so
installed helpers can parse them offline. Full YAML/frontmatter checks require PyYAML;
missing support is reported incomplete, never as a pass.

The catalog validator supports any standalone skill; it does not require bootstrap-specific
scripts. It checks links in references as well as SKILL.md, compiles Python without executing
it, and rejects linked resources. Reports contain `checked`, `errors` and `unverified` lists.
`partial` and `failed` both return exit code 1; only complete validation returns 0.
The unittest suite additionally exercises installation, generated profiles, Windows junctions
and the repository's actual GitHub configuration. Platform or dependency skips are explicit.

Keep SKILL.md concise with valid Agent Skills metadata and relative links. Put detailed
operations in references, generated files in assets, deterministic helpers in scripts.
Test observable preservation, conflicts and second-run behavior in temporary directories.
Do not fetch repositories or execute application builds in tests. Add only requested
skills, update the catalog and document their actual availability.

PR descriptions must explain resulting behavior, the actual diff, checks and limitations.
Repository owners configure branch protection and required reviews. Contributions are
provided under the project's MIT license. No automatic commits or publication occur.
