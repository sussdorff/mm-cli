# Guards

Deterministic checks that make the rule hold without relying on memory. Each
guard is a CI job or a registry setting; the standard states what the guard
verifies, the implementation lives with the repository or in a `script-forge`
script.

## Publisher side (SDK repository)

| Guard | Verifies | Fails when |
|-------|----------|------------|
| `version-bumped` (PR check) | Every `package.json` / `pyproject.toml` whose package has a diff against `main` carries a version greater than `main`'s | A changed package keeps its version, or the version went down |
| `bump-class-matches` (PR check) | The bump between `main` and the PR equals the class derived from the PR's commits per `bump-decision.md` | `feat` commits with only a PATCH bump; `!` commit without MAJOR |
| `canonical-semver` (PR check and publish gate) | `version` matches `^\d+\.\d+\.\d+$` | Any pre-release or build suffix |
| `one-version-per-merge` (publish gate) | The version being published has no existing tag and no registry entry | Re-publish of an existing version |
| `changelog-entry` (PR check) | The changed package's `CHANGELOG.md` gained an entry under the new version citing a Bead ID | Bump without changelog, or entry without Bead ID |
| `peer-range` (PR check) | Sibling packages of the family are declared in `peerDependencies` as ranges, not exact pins | Missing peer, or exact peer version |
| `scheme-declared` (repo config) | The repository release config states `version_scheme: semver` for the package (`release/release-lifecycle.md`) | Scheme missing or `calver` on an SDK |

Publish gates run in the tag-triggered workflow and refuse the publish; PR
checks block the merge.

## Consumer side (adapter, application)

| Guard | Verifies | Fails when |
|-------|----------|------------|
| `range-not-pin` (lint) | Every SDK dependency in the manifest is a caret or tilde range | Exact version in the manifest without a bead-cited exception comment |
| `no-pin-assert` (lint) | No test asserts the literal version of an SDK dependency | A contract test compares `dependencies["@x/y"]` to a string |
| `lockfile-consistent` (CI) | Install with frozen lockfile succeeds and `node_modules` matches the lockfile | Manifest and lockfile disagree |
| `renovate-configured` (repo check) | `renovate.json` exists, enables the private registry, and sets automerge for `patch` and `minor` on SDK packages | Missing or automerge off |
| `no-link-reference` (PR check) | No dependency in the manifest resolves to `link:`, `file:`, `workspace:` outside the package's own monorepo, or a git URL | A session-local co-development link reached the PR |
| `contract-reported` (CLI test) | A machine-consumed CLI reports the SemVer of the contract it implements alongside its CalVer binary version | `--version` or the envelope omits the contract version |

## Publisher publish-on-merge

| Guard | Verifies | Fails when |
|-------|----------|------------|
| `publish-on-merge` (workflow) | The merge to `main` publishes every bumped package; publishing is not a manual tag step for libraries | A bumped version exists on `main` without a registry entry |
| `image-tag-calver` (workflow) | The repository-level tag that builds images is CalVer and does not stamp package versions | A `v2026.x.y` tag rewrites a package's `version` |

## Registry side

| Setting | Effect |
|---------|--------|
| Immutable versions | A published version cannot be overwritten; a fix is a new PATCH |
| `npm deprecate <pkg>@"<range>" "<reason, replacement>"` | Consumers see the message at install time |

## Reference layout of a Renovate config for a consumer

```json
{
  "extends": ["config:recommended"],
  "hostRules": [{ "matchHost": "npm.cognovis.de", "token": "{{ secrets.NPM_TOKEN }}" }],
  "packageRules": [
    {
      "matchPackagePatterns": ["^@polaris/", "^@cognovis/"],
      "matchUpdateTypes": ["patch", "minor"],
      "automerge": true
    },
    {
      "matchPackagePatterns": ["^@polaris/", "^@cognovis/"],
      "matchUpdateTypes": ["major"],
      "automerge": false,
      "labels": ["sdk-major"]
    }
  ]
}
```

The MAJOR PR is the input to a consumer bead; the PR body carries the
changelog excerpt that names the migration.
