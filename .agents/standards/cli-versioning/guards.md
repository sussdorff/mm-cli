# CLI Versioning Guard Deltas

[`sdk-versioning/guards.md`](../sdk-versioning/guards.md) is canonical for
`version-bumped` and `changelog-entry`. This page adds only the per-tool CalVer
adaptations and CLI-only tag publication checks.

## SDK Guard Adaptations

`version-bumped` remains a PR-only guard. For an affected CLI it reads that
tool's manifest rather than a repository release number, parses `YYYY.M.N` as
the numeric tuple `(year, month, N)`, and compares those integer tuples. A
lexicographic string comparison is invalid: `2026.10.1` follows `2026.9.9`.

`changelog-entry` remains a PR-only guard. Its CLI adaptation requires the
affected tool's adjacent `CHANGELOG.md` heading for the bumped CalVer and its
Bead ID. The tag workflow has a separate `changelog-present` gate that confirms
the already-reviewed heading remains present; it does not recompute the PR
diff.

## CLI-Only Publication Guards

| Guard | Placement | Verifies | Fails when |
| --- | --- | --- | --- |
| `tag-matches-version` | Tag publish gate | `<tool>-vYYYY.M.N` identifies one package and equals its manifest version. | The tag is unscoped, malformed, or differs from the package manifest. |
| `trusted-release-tag` | Tag protection and tag publish gate | `<tool>-v*` is protected to the release actor, and its tagged commit is reachable from protected `main`. | An untrusted actor created the tag, protection is absent, or the commit bypasses protected main. |
| `one-release-per-version` | Registry and tag gate | The tool's CalVer has no prior release tag or registry artifact. | An existing tool version is republished. |
| `changelog-present` | Tag publish gate | The CLI's already-reviewed adjacent changelog contains the tagged CalVer heading. | The tag names a release missing its changelog heading. |
| `exact-pin-consumer-bump` | PR check | An exact pin change for a shared library includes the consuming CLI's CalVer bump and changelog entry. | A CLI silently absorbs an exact shared-library update. |
| `tests-before-publish` | Tag workflow | The configured package test command succeeds before build and index publication. | Build, publish, or release creation runs after a failed test. |
| `forge-release-recorded` | Tag workflow | The published artifact is represented by the matching Forgejo release. | The index contains an artifact without the scoped release record. |

`exact-pin-consumer-bump` does not apply to a caret, tilde, or other range
governed by `sdk-versioning`.

## Evidence

The tag workflow records the tool name, tag, manifest version, artifact digest
or Forgejo index URL, and Forgejo release URL. This evidence describes
publication only; it does not attest to an operational action outside Forgejo.
