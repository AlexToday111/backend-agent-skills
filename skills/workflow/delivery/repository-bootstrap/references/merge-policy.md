# Merge policy

| Operation | Policy |
| --- | --- |
| CREATE | Missing safe target; create exclusively. |
| PRESERVE | Identical file or existing docs/editor conventions; preserve bytes. |
| MERGE | Append missing literal ignore rules while retaining original text. |
| SKIP | Evidence insufficient or component inapplicable; report reason. |
| CONFLICT | Different YAML, another workflow, alternate Dependabot file, unsafe path, or ignore negations; manual review. |

Do not auto-merge arbitrary YAML or duplicate CI under another name. Preserve existing
issue settings, documentation and editor conventions. Ignore negations prevent automatic
additions because rule order changes semantics. Review broad pre-existing ignore rules;
adding patterns never untracks files. Conflicts are never forcibly resolved.

Modification through symlinks/junctions and non-directory parents is rejected. Select
the intended target root. The preflight cannot defend against a malicious concurrent
process swapping files; application requires a trusted root with no concurrent writers.
