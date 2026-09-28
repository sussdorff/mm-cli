# mm-cli Project Instructions

## Project Overview

CLI tool for MoneyMoney macOS app. Communicates via AppleScript (osascript). Requires MoneyMoney to be running and unlocked.

## Learnings

- **`bd` is a system-level CLI**, not a project dependency. Run it directly (`bd create`, `bd list`), not through `uv run bd`.
- **Always test against the real MoneyMoney app** after implementing changes, not just unit tests with mocks. Unit tests prove internal consistency but don't catch issues with real data shapes from the AppleScript API. Propose live testing proactively.
- **Check README accuracy after adding features.** When significant new functionality is added, verify the README reflects what actually exists — no phantom features, no missing capabilities.
