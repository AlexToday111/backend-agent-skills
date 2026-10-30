<h1 align="center">backend-agent-skills</h1>

<p align="center">
  Reusable Agent Skills for Java &amp; Go backend development.<br>
  Practical workflows. Explicit plans. Existing conventions preserved.
</p>

<p align="center">
  <strong>Java · Go</strong> &nbsp; / &nbsp; Python 3.10+ &nbsp; / &nbsp;
  <a href="https://agentskills.io/specification">Agent Skills format</a> &nbsp; / &nbsp;
  <a href="LICENSE">MIT license</a>
</p>

<p align="center">
  <a href="#available-skill">Skill</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#command-line">CLI</a> ·
  <a href="#development">Development</a> ·
  <a href="#roadmap">Roadmap</a>
</p>

---

<h2 align="center" id="available-skill">Available skill</h2>

**[repository-bootstrap](skills/workflow/delivery/repository-bootstrap/SKILL.md)** prepares
development infrastructure for new and existing repositories. It is the only implemented
skill; application business logic is outside its scope.

| Area | What it prepares |
| :--- | :--- |
| Project guidance | README and AGENTS instructions |
| Local conventions | Ignore rules and EditorConfig |
| Collaboration | Pull request template and issue forms |
| Automation | Applicable Java/Go CI and Dependabot updates |

Supports Maven, Gradle, Go Modules and mixed repositories. Unknown projects receive
general infrastructure without guessed build commands. Every operation is explicit:
`CREATE` · `PRESERVE` · `MERGE` · `SKIP` · `CONFLICT`.

---

<h2 align="center" id="quick-start">Quick start</h2>

With **Python 3.10+**, run from this repository's root. Replace the destination with your
project's path and choose your agent's supported discovery directory:

```sh
# Codex
python scripts/install_skill.py repository-bootstrap --destination /path/to/project/.agents/skills

# Claude Code
python scripts/install_skill.py repository-bootstrap --destination /path/to/project/.claude/skills
```

Then ask your agent:

> Use repository-bootstrap to inspect this repository, show the Standard profile plan
> and apply non-conflicting development infrastructure changes.

Clients with explicit invocation support can use **`$repository-bootstrap`**.
Compatibility follows the Agent Skills format; execution on every client is unverified.

The installer copies a standalone skill from [skills.json](skills.json), rejects linked
source resources and refuses overwrites. Updates require a reviewed reinstall.

---

<h2 align="center" id="command-line">Command line</h2>

Use the helpers directly for an offline, read-only plan, then apply it:

```sh
python skills/workflow/delivery/repository-bootstrap/scripts/bootstrap.py /path/to/target
python skills/workflow/delivery/repository-bootstrap/scripts/bootstrap.py /path/to/target --apply
```

**Java CI** requires an evidenced JDK, a reviewed local wrapper and an explicit
`--java-distribution` choice. Use `--java-distribution temurin` only when established for
the project; `--java-version` provides an optional explicit override. **Go CI** reads
`go.mod`. Missing prerequisites produce `SKIP`.

<details>
<summary><strong>Inspection, validation and idempotency</strong></summary>

```sh
python skills/workflow/delivery/repository-bootstrap/scripts/inspect_repository.py /path/to/target
python skills/workflow/delivery/repository-bootstrap/scripts/validate_configuration.py /path/to/target
python skills/workflow/delivery/repository-bootstrap/scripts/check_idempotency.py /path/to/target
```

Repeat the same Java options for idempotency checks. Reports use JSON and omit existing
file contents. Bootstrap exits with `0` for no failures/conflicts, `1` for failure and
`2` for unresolved conflicts; safe operations may still be applied. Skips remain unresolved.

See the [workflow](skills/workflow/delivery/repository-bootstrap/references/bootstrap-workflow.md),
[merge policy](skills/workflow/delivery/repository-bootstrap/references/merge-policy.md) and
[validation guide](skills/workflow/delivery/repository-bootstrap/references/validation.md).

</details>

**Boundaries:** helpers do not execute project code, use the network, commit, publish or
change remote settings. Generated CI needs network access when run. Structural checks
do not prove application builds or full GitHub schema compliance. Complex builds need
review; apply is non-transactional and requires no concurrent writers.

---

<h2 align="center" id="development">Development</h2>

Runtime helpers use the Python standard library. PyYAML is needed only for full validation;
Git is optional for inspection and required for Git fixture tests.

```sh
python -m pip install -r requirements-validation.txt
python scripts/validate_skills.py
python -m unittest discover -s tests/repository-bootstrap -v
```

Tests use temporary fixtures without external repositories or network calls. CI covers
Linux and Windows with Python 3.10 and 3.13. Without PyYAML, validation reports `partial`
and exits with `1`; catalog, resource-link, Python syntax and generated JSON checks still run.

| Path | Purpose |
| :--- | :--- |
| [skills/](skills/) | Skills with relative references, assets and runtime helpers |
| [scripts/](scripts/) | Catalog installation and repository validation |
| [tests/](tests/) | Offline behavioral tests |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution and verification guidance |
| [AGENTS.md](AGENTS.md) | Instructions for contributor agents |

---

<h2 align="center" id="roadmap">Roadmap</h2>

Four categories are planned: **Workflow · Development · Analysis · DevOps**.
Only implemented skills are shipped. Next: `requirements-analysis` and
`implementation-planning`.

<details>
<summary><strong>Workflow inventory — 1 implemented, 16 planned</strong></summary>

All entries below are **planned and unavailable**, except `repository-bootstrap`.

| Group | Skills |
| :--- | :--- |
| Planning | `requirements-analysis`, `implementation-planning`, `technical-decision-record`, `task-decomposition` |
| Development | `feature-implementation`, `safe-refactoring`, `bug-investigation`, `dependency-upgrade` |
| Quality | `change-impact-analysis`, `test-planning`, `pull-request-review`, `change-verification` |
| Delivery | **`repository-bootstrap` — implemented P0**, `pull-request-preparation`, `commit-management`, `release-preparation`, `technical-documentation` |

Development, Analysis and DevOps inventories will be defined in later milestones.

</details>
