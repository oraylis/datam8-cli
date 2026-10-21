# CI and package releases

Pull requests against `main` and pushes to `main` run the same short CI workflow.
Feature pushes and merged-PR events do not start another copy. Use a draft PR for
early feedback, or dispatch CI manually for the full checks.

The required `CI result` accepts successful documentation checks plus either all
quality jobs passing or their expected documentation-only skip. Markdown at the
repository root and Markdown/images under `docs/` use the documentation path;
`docs/signing/`, scripts, schemas, dependency files and submodule pins always use
the full checks. Failures, cancellations and unexpected skips block the result.

Lint/type analysis, package build/install smoke and pytest run in parallel.
Dependencies use the frozen uv lockfile. The existing legacy solution fixture is
pinned to commit `68001a2dcaa0b2931ee341f3527b96266a6e46da`; pytest receives its
path explicitly, without a global solution environment variable or live sources.
JUnit reports are uploaded even after a failing pytest run and retained 14 days.

## Explicit releases

The release workflow starts only when a protected `v*.*.*` tag is pushed.
Its name must equal `v` plus `project.version` in `pyproject.toml`, and its commit
must be reachable from `main`. DataM8 admins may create version tags; existing
version tags cannot be changed or deleted.

Release CI always runs every quality job. It builds the wheel and source archive
once and tests the installed wheel, including the API/offline ODCS smoke checks.
The publish job downloads these exact artifacts; it does not rebuild them.
It uploads them to a draft GitHub release before publishing. Python prerelease
versions produce GitHub prereleases. No tags or releases are created by a merge,
and this workflow does not publish to PyPI.

Build artifacts are retained for two days. Published GitHub release assets remain
available independently of that Actions retention. A failed upload leaves a draft
instead of exposing a partial public release; inspect that draft before retrying.

CodeQL uses the repository's existing default setup, independently of these jobs.
PR/Main CI supersedes stale runs; release runs are not automatically cancelled.
