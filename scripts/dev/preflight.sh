#!/usr/bin/env bash
# Pre-push preflight for mm-cli. The host's global pre-push hook runs this
# script when it is present in the repository.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

python3 .agents/standards/toolchains/scripts/check_toolchain_versions.py
