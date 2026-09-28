# Bump Decision

The version bump of a PR is a function of its commits. Humans and agents apply
the same table; the release guard recomputes it and refuses a mismatch.

## Commit type to bump class

| Commit signal | Bump | Notes |
|---------------|------|-------|
| `!` after type, or `BREAKING CHANGE:` footer | MAJOR | Any commit in the PR |
| `feat` | MINOR | New export, new option, new command, widened accepted input |
| `fix`, `perf`, `refactor`, `docs`, `test`, `chore`, `ci`, `build`, `style`, `revert` | PATCH | Includes dependency updates |
| PR with several commits | highest class present | MAJOR > MINOR > PATCH |

The floor is PATCH: a merged PR with no commits of any listed type still bumps
PATCH (invariant 1 of the entry file).

## What counts as breaking (MAJOR)

| Change | Breaking |
|--------|----------|
| Removing or renaming an exported symbol, command, flag, or config key | yes |
| Narrowing an accepted input type or value set | yes |
| Changing a return shape, an error code, or an exit code consumers match on | yes |
| Raising the minimum runtime (Bun, Node, Python) or a peer range's lower bound | yes |
| Changing default behaviour a consumer can observe without opting in | yes |
| Adding an optional field, export, command, or flag | no (MINOR) |
| Fixing behaviour to match documented intent | no (PATCH), unless consumers demonstrably depend on the defect |
| Internal refactor with identical public surface | no (PATCH) |

Type-only changes follow the same table: a widened TypeScript type is MINOR, a
narrowed one MAJOR.

## Agent instructions in factual form

- The bump is derived, not chosen: read the PR's commits, take the highest
  class, apply the floor.
- A `feat` that also removes something is MAJOR, not MINOR; the removal wins.
- Uncertainty between PATCH and MINOR resolves to MINOR; between MINOR and
  MAJOR it resolves to MAJOR. Over-bumping costs a number; under-bumping
  breaks a consumer's auto-merge.
- The commit type is authored with the bump in mind: a change that adds an
  export is `feat`, not `chore`, even when it feels small.
- Deprecation is `feat` (MINOR) with a `Deprecated` changelog entry; the
  removal in a later PR is MAJOR.

## Version sources

| Stack | Single source |
|-------|---------------|
| Node/Bun | `package.json` `version` per package (monorepo: one per package) |
| Python | `pyproject.toml` `[project] version` |

Tag format `<package>@<version>` in a monorepo, `v<version>` in a
single-package repo. No second copy of the version anywhere in the tree.
