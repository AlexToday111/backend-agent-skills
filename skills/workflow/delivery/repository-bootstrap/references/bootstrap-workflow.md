# Standard workflow

Inspect first, then plan. Both commands are offline and read-only. Review existing
conventions before applying the Standard profile. It covers README, AGENTS, ignore/editor
settings, PR/issue templates, CI and Dependabot. Components lacking evidence are SKIP;
missing language-job prerequisites are individually reported.

--include-content shows proposed CREATE content only, never existing or merged content.
--java-version is an explicitly selected JDK override; --java-distribution must come from
project convention or a user choice. Review the plan, then use --apply when authorized.
Application checks all mutation preconditions using hashes, creates missing targets
exclusively and applies only safe merges. It validates changed files after writing.

Exit 0: no errors/conflicts; 1: error/validation failure; 2: conflicts remain (safe
operations may still be applied). SKIP requires follow-up and is not a fabricated pass.
An I/O error may leave partial additions: inspect and rerun, never delete user files to
retry. Application is not transactional; stop concurrent writers during application.

Final report must cover inspection, operation table, applied files, validation scope and
results, conflicts, skips, assumptions and recommended follow-up. Helpers never initialize
Git, commit, publish, access the network or run application code.
