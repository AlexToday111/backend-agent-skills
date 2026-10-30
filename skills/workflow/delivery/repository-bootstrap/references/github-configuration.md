# GitHub configuration

Generated .yml files use formatted JSON, a YAML 1.2 subset accepted by GitHub. This keeps
runtime dependencies at zero. Existing ordinary YAML is preserved. Issue forms require
reproduction or use-case information; the PR template has Summary, Changes, Testing,
Breaking Changes, Risks and Checklist. Agents draft descriptions from actual diffs and
verification results; no automatic LLM API calls are configured.

CI uses push/pull_request events, contents: read, checkout persist-credentials: false,
bounded jobs, no secrets and no pull_request_target. Maintained official action major
versions are tracked by Dependabot weekly. For a stricter policy, resolve and review
full commit SHAs before pinning; never invent SHAs. Setup actions and wrappers download
toolchains and dependencies when remote CI runs. Local creation does not authorize push.

Recommend required reviews, default-branch protection, appropriate CODEOWNERS, restricted
workflow tokens, and required checks after real CI passes. Do not automatically change
repository settings or invent team handles, labels, branch names or URLs. Differing
existing automation is a conflict for review. Remote validation is unverified until run.

Action versions checked on 2026-10-27 against official repositories:
https://github.com/actions/checkout, https://github.com/actions/setup-python,
https://github.com/actions/setup-java, https://github.com/actions/setup-go.
