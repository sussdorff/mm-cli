# Changelog

## [0.1.0] - 2026-04-16

### Added
- Initial PyPI release as `moneymoney-cli`
- `mm accounts` — list accounts with balances, hierarchy, and group filtering
- `mm transactions` — fetch transactions with date ranges, categories, amount filters, sorting, and checkmark filters
- `mm categories` — view categories with hierarchy and rules
- `mm category-usage` — show categories ranked by usage
- `mm set-category`, `mm set-checkmark`, `mm set-comment` — reconciliation workflows
- `mm analyze spending/cashflow/recurring/merchants/top-customers/balance-history` — financial analysis with transfer filtering and period comparison
- `mm portfolio` — investment portfolio across depot accounts
- `mm transfer` — initiate SEPA transfers with dry-run, outbox, and confirmation modes
- `mm export` — export to MT940/STA, CSV, OFX, CAMT.053, XLS, Numbers
- `mm suggest-rules` — suggest MoneyMoney categorization rules from uncategorized transactions
- `mm init` — interactive setup for transfer category and excluded account groups
- XDG-compliant config at `$XDG_CONFIG_HOME/mm-cli/config.toml` (fallback `~/.config/mm-cli/config.toml`)
- Global `--version` flag
- Output formats: `table` (default), `json`, `csv` on all commands
- MIT license
