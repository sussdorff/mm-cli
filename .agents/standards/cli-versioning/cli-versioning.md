---
rule: cli-versioning
description: Independently distributed CLI binaries use per-tool CalVer releases, tagged publication, and per-tool changelogs while their machine contracts remain SemVer.
---

# CLI Versioning

> **Scope**: Loaded by release skills and tag workflows that publish an operator
> CLI. It states the binary-release contract; `sdk-versioning` remains the
> contract-versioning rule for imported libraries and machine-consumed protocols.

## Rule

Each distributable CLI has its own CalVer `YYYY.M.N`. `YYYY` is the release
year, `M` the calendar month, and `N` the next release number for that CLI in
that month. The version belongs to the CLI package manifest; a repository root
or another CLI never supplies a second version source. The release workflow
checks the manifest against the tag; it does not stamp the manifest.

| Artifact | Version and release identity | Reason |
| --- | --- | --- |
| CLI binary or wheel | Per-tool CalVer `YYYY.M.N`; tag `<tool>-vYYYY.M.N` | Operators identify a freshly published executable without coupling unrelated tools. |
| CLI protocol (commands, exit codes, JSON envelopes, error codes) | SemVer contract under `sdk-versioning` | Programs need a compatibility signal, not a publication date. |
| Shared imported library | SemVer under `sdk-versioning` | Consumers resolve a declared compatibility range. |

A CLI package is a package with an operator-invokable executable entry point.
An imported support library remains an `sdk-versioning` library even when it
lives beside a CLI package or is released from the same repository. Publishing
a CLI package does not turn its imported support libraries into CLI releases.

A tag release is a new CLI version: its `<tool>-vYYYY.M.N` tag, package manifest, built artifact,
and new `CHANGELOG.md` heading carry the same CalVer. A release tag names one
tool only. A tool's changelog is adjacent to its package and contains only that
tool's release history; a repository-wide changelog is not its substitute.

Each protected `<tool>-v*` tag is created only by the declared release actor.
Before tests, build, or publication, the workflow verifies both that protection
and that the tagged commit is reachable from protected `main`.

An exact-pinned shared-library change is coupled to its consuming CLI release:
the same change increments that CLI's CalVer and adds its changelog entry.
Range-based SDK consumers remain governed by `sdk-versioning`.

## Forgejo Actions Boundary

Forgejo Actions are artifact-only. They may run hermetic checks, build
artifacts, compute artifact digests, publish artifacts to Forgejo package
registries, and create Forgejo release records. They must not invoke operational
CLI commands and must not access customer, product, or control-plane systems.

The workflow may package the CLI that it publishes, but packaging is not an
invocation of that CLI's operational target commands. Any operation that acts
on a customer, a product environment, a deployment target, or a control plane
belongs to a separately authorized operator workflow outside Forgejo Actions.

## Marketplace Distribution

The Standards v2 source is this folder: `standards/cli-versioning/`. Its entry
file makes the folder and its linked detail pages discoverable by the
marketplace's source inventory. The active `library.yaml` is an installer
projection, not a source file in this repository; no parallel catalog entry is
authored here. Consumers reach the standard through an explicit
`requires_standards: [cli-versioning]` declaration.

## References

- [guards.md](guards.md) records the deterministic publication and consumer
  guards.
- [workflow-template.md](workflow-template.md) records the tag-workflow shape.
- `sdk-versioning` owns SemVer, SDK ranges, and machine-consumed CLI contracts.
- `release` owns the common changelog conventions and release metadata lifecycle.
