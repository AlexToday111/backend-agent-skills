# Java configuration

Detection never executes plugins or downloads wrappers. Review wrapper integrity before
remote CI runs them. Maven requires mvnw and .mvn/wrapper/maven-wrapper.properties;
modern script-only wrappers are supported. Gradle additionally requires its wrapper JAR
and gradle/wrapper/gradle-wrapper.properties. Missing wrappers are reported, not invented.

CI requires a literal JDK detected in configuration or explicit --java-version, plus
--java-distribution selected from repository convention or user preference. No JDK vendor
is guessed. Maven runs bash ./mvnw --batch-mode verify; Gradle runs
bash ./gradlew build --no-daemon. These are standard build entry points, not a claim that
custom quality tasks exist. Review unusual Gradle builds and customize manually as needed.

Each detected build root receives its own job. Nested independent Java builds and reactor
submodules may overlap and need job consolidation after build graph review. Inherited
Maven settings, complex Gradle DSL, multi-JDK and non-Linux builds need manual configuration.
Dependabot uses the detected maven/gradle manifest directories.
