---
rule: sdk-versioning
description: Artifacts with a programmatic contract (SDKs, libraries, kits, CLI protocols) use strict SemVer published on every merge; independently distributed CLI binaries use CalVer; consumers take ranges and bot-driven updates.
---

# SDK Versioning

> **Scope**: Loaded when a package that other code imports or parses is
> versioned, published, or consumed, and when a repository decides which
> scheme an artifact carries. `cli-versioning` carries the independent-operator
> CLI CalVer and tag mechanics; this rule decides which artifact gets which.

## Rule

The axis is **contract versus implementation**, not "SDK versus CLI".

| Artifact | Scheme | Why |
|----------|--------|-----|
| Library, SDK, kit, client, type bundle (`@polaris/*`, `@cognovis/*`, Python packages other repos import) | SemVer `MAJOR.MINOR.PATCH`, one version per package | The number must carry the *meaning* of the change so ranges and bots can act on it |
| Machine-consumed CLI protocol (JSON envelopes, error codes, exit codes, command names) | SemVer, versioned as its own package or a `contract` field the CLI reports | Agents and other programs match on it; a date cannot say what broke |
| Independently distributed CLI binary | CalVer under `cli-versioning`; generic Python mechanics remain in `python-cli-patterns/versioning-release.md` | Freshness is the message; the contract it implements is versioned separately |
| Service, application, container image | Per-artifact scheme declared by its release contract | A service can carry a SemVer release independently of its image build |
| Monorepo of loosely coupled packages (polaris) | Each package its own independent SemVer; the repository tag stays CalVer and names the image build | Packages move at different speeds; the image is an implementation |

An artifact is a library when at least one other repository lists it as a
dependency. The first external consumer moves it to `>= 1.0.0`; the `0.x`
escape in `release/changelog.md` applies only before that point.

**Publisher invariants**

1. Every PR merged to `main` that touches a package bumps that package at
   least by PATCH and publishes it from the merge. Two merges never share a
   version; a touched package without a bump is a CI failure.
2. The bump class is derived from the PR's Conventional Commit types
   ([bump-decision.md](bump-decision.md)); an agent applies the same table.
3. Published versions are canonical SemVer with no pre-release or build
   suffix (`-pkg.1`, `-ballot`, `-rc.1`, `+sha`). A broken publish is
   followed by a PATCH, never retracted. Third-party FHIR IG packages with
   ballot suffixes are consumed, never produced.
4. `CHANGELOG.md` per package, generated from commits, every entry citing its
   Bead ID (`release/changelog.md` format).
5. Packages of one family declare each other as `peerDependencies` ranges,
   so an inconsistent install fails at install time.
6. A version consumers must leave is marked with `npm deprecate` naming the
   replacement.
7. A library is not proven by a consumer. A consumer's need is stated in the
   library bead as RED tests before implementation (`tdd-authoring`); the
   library ships when its own tests are green.

**Consumer invariants**

8. Manifest carries a caret range (`^1.4.0`); the lockfile carries the exact
   version. Reproducibility comes from the lockfile, never from an exact pin
   plus a test asserting the pin.
9. Update discovery is a bot (Renovate against Forgejo and `npm.cognovis.de`)
   opening one PR per update with the changelog excerpt. PATCH and MINOR
   auto-merge on green CI; MAJOR is merged by a human or a bead naming the
   migration. No prose or bead note asks "is there something newer".
10. Co-developing a library and its consumer in one session uses `bun link`,
    a workspace, or `file:` — locally only. A manifest that reaches `main`
    references a published version; the guard in
    [guards.md](guards.md) refuses link and file references.

## Exceptions

- One `package.json` serving a CLI and a library is split into two packages.
- An exact pin in a consumer is permitted only inside a bead naming the
  reason (a known-bad range) and carrying the follow-up to remove it.

## Related Standards

- `release` — SemVer bump table, changelog format, tag flow.
- `git` — Conventional Commit types the bump decision reads.
- `cli-versioning` — per-tool CalVer, release guards, and tag-workflow shape
  for independently distributed CLI binaries.
- `python-cli-patterns` — generic Python CLI release mechanics when
  `cli-versioning` does not apply.
- `tdd-authoring` (skill) — how a consumer's need becomes RED tests.
