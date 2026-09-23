# Forgejo Registry (private distribution)

Public PyPI is for public tools. Private Cognovis CLI tools are published to
the Forgejo PyPI package registry on `git.cognovis.de` and installed from
there with `uv tool install` — no git checkout and no repository credentials
needed on the target machine.

## When to Use

- The tool is private (`LicenseRef-Proprietary`, internal repository).
- The tool must be installable and upgradable on machines that have no access
  to the source repository (servers, CI, third-party machines).

Public tools keep the generic PyPI + Trusted Publishing flow from
`versioning-release.md` — this file replaces that flow for private tools.
Independent Cognovis operator CLIs use `cli-versioning` for their version,
scoped tag, and workflow; this page supplies only their private-index mechanics.

## Publish

Registry endpoint (owner is the Forgejo org or user, usually `cognovis`):

```text
https://git.cognovis.de/api/packages/cognovis/pypi
```

Upload the wheel with twine (via `uvx`, no project dependency):

```bash
set -a; . ~/forgejo-shikigami.env; set +a   # FORGEJO_URL, FORGEJO_TOKEN
uv build
TWINE_USERNAME=<forgejo-user> TWINE_PASSWORD="$FORGEJO_TOKEN" \
  uvx twine upload --non-interactive --disable-progress-bar \
  --repository-url "$FORGEJO_URL/api/packages/cognovis/pypi" \
  dist/<package>-<version>-py3-none-any.whl
```

Use a token with `write:package` scope. Tokens without package scope
authenticate but the upload fails with `401 reqPackageAccess`.

Do NOT upload with bare `curl -F content=@...`: Forgejo validates the full
PyPI upload form including `sha256_digest` and rejects partial forms with
`400 hash mismatch`. twine sends the complete form.

Re-uploading an identical version is rejected — bump the version first.
twine only uploads the named file, so pass the wheel explicitly (or clean
`dist/`) to avoid duplicate-version errors from stale artifacts.

## Install on a target machine

One-time setup: register the index and credential. The credential is a
read-only package token — repository access is not required.

```toml
# ~/.config/uv/uv.toml
[[index]]
url = "https://<user>:<token>@git.cognovis.de/api/packages/cognovis/pypi/simple"
```

Then:

```bash
uv tool install <package>
uv tool upgrade <package>        # real version semantics, unlike git sources
```

Ad-hoc without config:

```bash
uv tool install \
  --index-url "https://<user>:<token>@git.cognovis.de/api/packages/cognovis/pypi/simple" \
  <package>
```

## Why not `uv tool install git+https://...`

- Repository credentials on every target machine, per repository.
- No clean upgrade semantics: uv only re-resolves the ref, there is no
  version comparison, so `uv tool upgrade` does not work as expected.
- The registry path gives one index and one token for all private tools.

**Why twine over curl:** the upload form contract (digests, metadata fields)
is the PyPI legacy upload API; twine implements it, a hand-rolled form breaks
silently on Forgejo upgrades.
