# Contributor agent instructions

This repository contains reusable skills, not application scaffolds. Implement only
requested skills; roadmap entries are not available capabilities. Read the relevant
SKILL.md and references first. Keep installed skills standalone with relative links.
Use Python 3.10+ and prefer standard-library runtime helpers. Preserve deterministic
plans, custom configuration and idempotency. Never expose secrets or run inspected code.

Run python scripts/validate_skills.py and
python -m unittest discover -s tests/repository-bootstrap -v.
Use temporary fixtures only, without external repositories or network calls. Report
partial validation when YAML support is absent. Do not commit, push or publish without
explicit authorization. Planned categories must not acquire empty placeholder skills.
