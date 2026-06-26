# Changelog


## [Unreleased]



### Added

- **mm-cli-4zd:** Green — AC1 Streamable-HTTP MCP server with bearer auth

- **mm-cli-4zd:** Green — AC2–AC7 read tools use Any for presence error schema


### Documentation

- **mm-cli-4zd:** Update changelog and README for mm serve MCP server command


### Fixed

- **mm-cli-4zd:** Use secrets.compare_digest for constant-time bearer token comparison

- **mm-cli-4zd:** Address codex adversarial findings — ioreg parse robustness and loopback fallback error


### Tests

- **mm-cli-4zd:** Red — AC1 MCP server endpoint lists tools

- **mm-cli-4zd:** Red — AC2–AC7 acceptance criteria tests



## [v2026.06.2] - 2026-06-26



### Added

- **mm-cli-bky:** Add --fields JSON selector, verify accountName and category-usage JSON


### Changed

- Commit main-repo working tree updates (.gitignore and PRIME) before feature merge

- Add beads runtime artifact gitignore entries and update PRIME

- Resolve conflicts with origin/main (pagination + JSON shaping)

- **mm-cli-bky:** Update changelog for mm-cli-bky session close

- Worktree-bead-mm-cli-bky (Backend hardening: JSON shaping --fields, accountName, category-usage json)

- Bump version to 2026.06.2



## [v2026.06.1] - 2026-06-26



### Changed

- 

- Commit generated files before second merge (worktree-bead-mm-cli-lgq)

- Worktree-bead-mm-cli-lgq

- Bump version to 2026.06.1



## [v2026.06.0] - 2026-06-26



### Changed

- Commit generated files before bead merge (worktree-bead-mm-cli-xtq)

- Commit generated files before second merge (worktree-bead-mm-cli-xtq)

- Worktree-bead-mm-cli-xtq

- Bump version to 2026.06.0



## [v0.1.3] - 2026-06-26



### Added

- **mm-cli-xtq:** Add --limit/--offset/--count for transactions and --months for analyze spending


### Changed

- **mm-cli-lgq:** Fix CLI I/O hygiene - stdout/stderr/exit, version json, no-color

- **release:** Prepare v0.1.3



## [v0.1.2] - 2026-06-08



### Changed

- **release:** Prepare v0.1.2



## [v0.1.1] - 2026-06-06



### Changed

- **beads:** Migrate to bd v1.0.0 and harden ignore rules

- Update beads state

- **release:** Prepare v0.1.1


### Documentation

- Add project-context


### Fixed

- Inherit active account group exclusions



## [v0.1.0] - 2026-04-16



### Added

- Fix category hierarchy and add suggest-rules command

- Add account groups/hierarchy and spending analysis

- Add IBAN-based transfer detection and analysis commands

- Add portfolio, transfer, set-checkmark, set-comment commands and extend transaction filtering

- Add --transfers-only flag to all analyze subcommands

- Add user config file and mm init command


### Changed

- Initial project setup with beads

- UV project with Python 3.14
- Basic CLI structure with typer
- Two beads for tracking work:
  - mm-cli-ezy: Core CLI commands (accounts, transactions, categories)
  - mm-cli-bee: Additional AppleScript functionality (transfers, portfolio)

- Implement core CLI commands for MoneyMoney interaction

- Add data models (Account, Category, Transaction, CategoryUsage)
- Implement AppleScript interface for MoneyMoney communication
- Add CLI commands: accounts, categories, transactions, category-usage, set-category
- Rich terminal output with colored tables
- Support for JSON and CSV output formats
- 36 unit tests with full coverage of core functionality

Closes: mm-cli-ezy

- Fix AppleScript parsing for real MoneyMoney output

- Handle plist XML returned directly (not as file path)
- Parse nested balance arrays: [[amount, currency]]
- Handle dict wrapper with 'transactions' key
- Convert datetime objects to date for transaction dates
- Extract category name from path (e.g., 'A\B\C' -> 'C')
- Add German account type names (Girokonto, Sparkonto, etc.)
- Skip account groups in export
- Update test fixtures to match real MoneyMoney structure

- Add export command for MT940/STA and other formats

- Add format parameter to export_transactions() supporting csv, ofx, sta, xls, numbers, camt.053
- Add 'mm export' CLI command with --format (default: sta), --account, --from, --to, --output options
- Non-plist formats return file path to temporary file
- Tested successfully with Collmex MT940 import

- Add .claude to gitignore

- Add amazon orders extraction task (mm-cli-37h)

- Close mm-cli-37h - using azad extension for amazon orders

- **release:** Prepare v0.1.0 for PyPI as moneymoney-cli


### Documentation

- Add Configuration section for mm init


### Fixed

- Add --days default, portfolio AppleScript, balance-history rendering

- Add -h help flag, suggest-rules default date range, locked db error


