# Validation

Installed runtime: Python 3.10+, standard library only. Git is optional for inspection
and required for Git fixture tests. Scripts never install dependencies or use networks.

Run python <skill>/scripts/validate_configuration.py <target>. Structural validation
checks generated YAML/JSON, workflow events/jobs/permissions, checkout credentials,
issue fields, Dependabot entries, PR sections and editor settings. Ordinary YAML needs
optional PyYAML 6.0.3; absence is reported as unverified with nonzero exit. Custom files
can fail the strict generated-profile checks without being invalid for GitHub; never
rewrite them just to satisfy this checker. Apply checks changed and byte-identical generated files; custom preserved files stay unverified.

Run python <skill>/scripts/check_idempotency.py <target> with the same Java options.
It applies twice in a temporary copy, checks hashes and the second write set. Source is
untouched; .git, generated directories and links are excluded. Conflicts are reported
separately: idempotency does not prove completeness.

Nested Git repositories are excluded from the temporary copy, matching inspection.
Conflicts from the original plan and both copied passes are retained, so excluding a
linked configuration cannot hide an unresolved source conflict. Windows reparse points
are rejected on all supported Python versions, including 3.10 and 3.11.

Contributors run python scripts/validate_skills.py and
python -m unittest discover -s tests/repository-bootstrap -v. CI uses Python 3.10/3.13 on
Linux/Windows with requirements-validation.txt (pinned PyYAML, validation-only). Full
GitHub schema, actionlint, application builds and remote execution remain separate.

The idempotency CLI returns 2 for stable execution with unresolved conflicts, 1 for a
failed check, and 0 for stable execution without conflicts. Both passes are validated.
