# Versioning and Release

## CalVer

Use Calendar Versioning: `YYYY.0M.MICRO` (e.g. `2026.03.0`, `2026.03.1`). Tag
format: `v2026.03.0` (leading zero in the month).

PyPI normalizes versions — leading zeros are stripped: `2026.03.2` becomes
`2026.3.2`. When comparing installed vs latest, normalize before comparison:

```python
def normalize_version(version: str) -> str:
    """Normalize CalVer: '2026.03.2' -> '2026.3.2' to match PyPI."""
    return ".".join(str(int(p)) if p.isdigit() else p for p in version.split("."))
```

**Why CalVer:** Communicates release freshness at a glance. SemVer is overkill
for tools without a public API contract.

## Release Workflow

Tag-triggered CI: push a `v*` tag, then tests, stamp version, build, publish,
GitHub Release.

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
      - name: Stamp version
        env:
          VERSION: ${{ steps.version.outputs.VERSION }}
        run: |
          sed -i "s/^version = .*/version = \"$VERSION\"/" pyproject.toml
          sed -i "s/^__version__ = .*/__version__ = \"$VERSION\"/" src/my_tool/__init__.py
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

Do NOT use `UV_PUBLISH_TOKEN`, `TWINE_PASSWORD`, or long-lived PyPI API tokens.

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
