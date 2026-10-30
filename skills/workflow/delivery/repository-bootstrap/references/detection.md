# Detection

The inspector uses read-only Git rev-parse calls. It distinguishes absent Git, no Git
repository, unborn HEAD, commits, worktree .git files and an enclosing parent repository.
It never reports remote URLs, credential contents or Git status filenames.

Search is deterministic. Generated/vendor directories, nested Git repositories,
symlinks and junctions are excluded. Manifests are pom.xml, build.gradle(.kts), go.mod
at any depth. Source-only Java/Go without a manifest remains unknown. Reading a manifest
is capped at 1 MB. Warnings report failed inspection without printing source excerpts.

Maven accepts literal direct properties; inherited parents, profiles, plugin configuration
and property interpolation require manual inspection. XML entities/DOCTYPE are rejected.
Gradle accepts a single literal JavaLanguageVersion.of declaration and never evaluates
build logic. Go uses a literal go directive. Review conditional Gradle logic, toolchain
vendor constraints and go.work before accepting the inferred CI commands.
