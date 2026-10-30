# Go configuration

Each go.mod creates a separate module job, including nested modules. setup-go reads the
actual go.mod version using go-version-file, without a guessed latest/stable toolchain.
Cache is disabled so new modules without go.sum work. Tests run go test ./... within the
module directory. go.sum is never ignored. Dependabot uses gomod at the actual directory.

Review go.work replacement paths, toolchain directives, cgo dependencies and private
modules. No credentials are generated. The helper does not run go mod tidy, download
modules or execute application tests. Those checks need separately appropriate authority
for network access and untrusted project code. Existing CI remains authoritative.
