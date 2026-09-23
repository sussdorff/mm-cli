# Versioning and Release

## Applicability

This page is the default for standalone Python CLIs that do not declare
`cli-versioning`. Independently distributed Cognovis operator CLIs load
`cli-versioning`; it is authoritative for their unpadded `YYYY.M.N` CalVer,
`<tool>-vYYYY.M.N` tag syntax, manifest version source, and Forgejo workflow.
The generic rules below do not combine with that operator-CLI contract.

## Generic CalVer

Use Calendar Versioning: `YYYY.0M.MICRO` (e.g. `2026.03.0`, `2026.03.1`). Tag
format: `v2026.03.0` (leading zero in the month).

PyPI normalizes versions — leading zeros are stripped: `2026.03.2` becomes
`2026.3.2`. When comparing installed vs latest, normalize before comparison:

```python
def normalize_version(version: str) -> str:
    """Normalize CalVer: '2026.03.2' -> '2026.3.2' to match PyPI."""
    return ".".join(str(int(p)) if p.isdigit() else p for p in version.split("."))
```

**Why CalVer:** The binary is an implementation; freshness is the message.
CalVer applies to the CLI binary only. A library, SDK, or kit that other
repositories import carries SemVer per `sdk-versioning`, and a CLI whose
output other programs parse (JSON envelopes, error codes, exit codes) reports
the SemVer of that contract alongside its CalVer binary version — the contract
lives in its own SemVer package (for example a `*-cli-kit`) or a `contract`
field in `--version` output.

## Generic Single Version Source

For this generic flow, `pyproject.toml` is the release manifest and CI stamps
it from the tag. Do not add a `VERSION` file, and do not keep a second copy of
the version beyond the CI-stamped `__version__`. Every additional source can
drift silently — nothing forces the copies to agree. Operator CLIs instead keep
their version in the manifest before tagging and the workflow verifies equality
under `cli-versioning`.

Release preparation verifies that `pyproject.toml` and the newest release tag
agree before it tags. That single check replaces multi-source agreement
guards.

## Generic Release Workflow

Tag-triggered CI: push a `v*` tag, then tests, stamp version, build, publish,
GitHub Release.

Author workflow steps as one command per step. Orchestration logic — version
checks, changelog rendering, publish guards — belongs in a command the
workflow calls, not in multi-line inline shell. Inline shell blocks drift
between repositories and cannot be tested.

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags: ["v[0-9]*"]

permissions:
  contents: write
  id-token: write

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv run pytest -v

  publish:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - name: Extract version from tag
        id: version
        run: echo "VERSION=${GITHUB_REF_NAME#v}" >> $GITHUB_OUTPUT
      - name: Stamp pyproject version
        env:
          VERSION: ${{ steps.version.outputs.VERSION }}
        run: sed -i "s/^version = .*/version = \"$VERSION\"/" pyproject.toml
      - name: Stamp module version
        env:
          VERSION: ${{ steps.version.outputs.VERSION }}
        run: sed -i "s/^__version__ = .*/__version__ = \"$VERSION\"/" src/my_tool/__init__.py
      - run: uv build
      - run: uv publish --trusted-publishing always
      - uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.ref_name }}
          name: Release ${{ steps.version.outputs.VERSION }}
```

## Trusted Publishing (OIDC)

For PyPI uploads, use Trusted Publishing instead of API tokens:

1. PyPI project, Settings, Publishing, Trusted Publishers
2. Add GitHub publisher: owner, repo, workflow filename
3. In the workflow: `uv publish --trusted-publishing always` — no secrets needed.

For public PyPI uploads, do NOT use `UV_PUBLISH_TOKEN`, `TWINE_PASSWORD`, or
long-lived PyPI API tokens.

Private tools do not go to public PyPI at all — they publish to the Forgejo
registry with a package-scoped token and twine. See
[forgejo-registry.md](forgejo-registry.md).

**Why:** OIDC tokens are short-lived, scoped to the specific workflow run, and
cannot leak or be reused.

## `uv tool upgrade` — Force-Refresh

`uv tool upgrade <package>` ignores uv's package cache and may report
"Nothing to upgrade" even when a newer version was just published.

```bash
# Correct — bypasses cache and fetches the latest index
uv tool install <package> --force --refresh
```

In auto-update implementations:

```python
subprocess.run(["uv", "tool", "install", package, "--force", "--refresh"])
```
