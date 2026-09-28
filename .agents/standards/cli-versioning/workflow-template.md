# Per-CLI Tag Workflow Template

A publication workflow is scoped to one CLI tag pattern. Its inputs identify a
tool and CalVer without inferring either from a repository-wide release.
Each generated per-tool workflow substitutes `TOOL` and
`PACKAGE_TEST_COMMAND`, which is the hermetic package check run before build
or publication. `<runner-label>`, `<package-build-command>`,
`<package-publish-command>`, `<forgejo-release-command>`, and
`<trusted-source-check-command>` are repository-supplied interfaces, not
installed command names. Neither the package check nor these interfaces invokes
the published CLI's operational commands or accesses a customer, product, or
control-plane system.

```yaml
name: Publish <tool>

env:
  TOOL: <tool>
  PACKAGE_TEST_COMMAND: <package-test-command>
  RELEASE_ACTOR: <release-actor>
  PROTECTED_BRANCH: main
  TRUSTED_SOURCE_CHECK_COMMAND: <trusted-source-check-command>

permissions:
  contents: read

on:
  push:
    tags:
      - "<tool>-v[0-9]*"

jobs:
  verify:
    runs-on: <runner-label>
    outputs:
      tag: ${{ steps.release.outputs.tag }}
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          fetch-depth: 0
      - name: Bind scoped tag and raw CalVer
        id: release
        env:
          REF_NAME: ${{ github.ref_name }}
        run: |
          TAG="$REF_NAME"
          VERSION="${TAG#${TOOL}-v}"
          test "$TAG" = "${TOOL}-v$VERSION"
          printf '%s\n' "$VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'
          printf 'tag=%s\n' "$TAG" >> "$GITHUB_OUTPUT"
      - name: Verify trusted protected source
        env:
          RELEASE_TAG: ${{ steps.release.outputs.tag }}
        run: $TRUSTED_SOURCE_CHECK_COMMAND --tag "$RELEASE_TAG" --required-actor "$RELEASE_ACTOR" --require-protected-tag --require-reachable-from "$PROTECTED_BRANCH"
      - name: Verify tag, uniqueness, and changelog presence
        env:
          RELEASE_TAG: ${{ steps.release.outputs.tag }}
        run: uv run scripts/verify_cli_release.py --tool "$TOOL" --tag "$RELEASE_TAG" --require-unique --require-changelog
      - name: Test package
        run: $PACKAGE_TEST_COMMAND
  publish:
    needs: verify
    runs-on: <runner-label>
    permissions:
      contents: write
      packages: write
    env:
      PACKAGE_PUBLISH_TOKEN: ${{ secrets.PACKAGE_PUBLISH_TOKEN }}
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          fetch-depth: 0
      - name: Build wheel or package
        run: <package-build-command>
      - name: Publish to package index
        run: <package-publish-command>
      - name: Create Forgejo release
        env:
          RELEASE_TAG: ${{ needs.verify.outputs.tag }}
        run: <forgejo-release-command> --tag "$RELEASE_TAG" --asset <artifact>
```

The tag helper embodies `tag-matches-version`, `one-release-per-version`, and
tag-time `changelog-present` from [guards.md](guards.md).
`version-bumped` and the full changelog-diff check remain PR-only guards. The
package build begins only after verification; index publication precedes the
Forgejo release record so that the release links to a real artifact. `verify`
publishes its tag as a job output, so `publish` never reaches across a job to a
step output.

The examples name stable interfaces rather than credentials. Registry
authentication is a package-scoped CI secret available only to `publish`; no
step prints or forwards its value. The trusted-source check reads the protected
tag policy and full Git history before the test, build, or publish path. The
workflow boundary ends with Forgejo publication and its release record; an
operator action against any runtime environment is a separate, explicitly
authorized process.
