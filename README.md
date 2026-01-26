# mm-cli

A command-line interface for [MoneyMoney](https://moneymoney-app.com/) on macOS. Talks to MoneyMoney via AppleScript to give you fast, scriptable access to your accounts, transactions, and categories — directly from the terminal.

## Requirements

- macOS (required for AppleScript)
- [MoneyMoney](https://moneymoney-app.com/) installed and running
- Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
git clone <repo-url>
cd mm-cli
uv sync
```

All commands are available via `mm`. Run `mm --help` for a full list, or `mm <command> --help` for details on any command.

## What you can do

### See your accounts and balances

View all accounts with their current balances, grouped by the account groups you've set up in MoneyMoney:

```bash
mm accounts
```

You can see them organized by group with subtotals using `mm accounts --hierarchy`, or focus on specific groups with `mm accounts --group Privat`. To exclude closed accounts, use `mm accounts --active`.

### Browse and filter transactions

Pull transactions with date ranges, category filters, or find uncategorized ones:

```bash
mm transactions --from 2026-01-01 --to 2026-01-31
mm transactions --category Lebensmittel
mm transactions --uncategorized
```

Filter by account with `--account <IBAN>`.

### Analyze your finances

All analysis commands filter out internal transfers (Umbuchungen) by default — both by IBAN matching against your own accounts and by MoneyMoney's transfer category tree. When using `--group`, cross-group transfers (e.g. salary from your company account to your personal account) are kept as real cashflow. Use `--include-transfers` to disable filtering.

**Spending by category** — see where your money goes, with budget tracking:

```bash
mm analyze spending
mm analyze spending --period last-month --compare
mm analyze spending --type expense --group Privat
```

**Cashflow** — income vs expenses over time:

```bash
mm analyze cashflow --months 6
mm analyze cashflow --months 12 --period quarterly
mm analyze cashflow --group Privat
```

**Recurring transactions** — detect subscriptions and standing orders:

```bash
mm analyze recurring --months 12
mm analyze recurring --min-occurrences 4
```

**Merchants** — top merchants by total spend:

```bash
mm analyze merchants
mm analyze merchants --type all --limit 20
```

**Top customers** — income grouped by counterparty:

```bash
mm analyze top-customers
mm analyze top-customers --period this-year
```

**Balance history** — approximate historical balance per account:

```bash
mm analyze balance-history --months 6
mm analyze balance-history --account Girokonto
```

### Export transactions to other formats

Export to MT940/STA (for accounting software), CSV, OFX, CAMT.053, XLS, or Numbers:

```bash
mm export --from 2025-01-01 --to 2025-12-31 --format csv -o ~/export.csv
mm export --account "DE89..." --format sta
```

### Manage categories

View all categories with their hierarchy and existing rules:

```bash
mm categories
```

See which categories are used most (by transaction count) with `mm category-usage`.

To re-categorize a transaction:

```bash
mm set-category <transaction-id> Lebensmittel
mm set-category <transaction-id> Lebensmittel --dry-run  # preview first
```

### Get rule suggestions for uncategorized transactions

Analyzes your uncategorized transactions, looks at historical patterns from already-categorized ones, and suggests MoneyMoney rules you could create:

```bash
mm suggest-rules --from 2026-01-01
mm suggest-rules --history 12  # use 12 months of history for better matches
```

### Output formats

Every command supports `--format table` (default), `--format json`, and `--format csv`. JSON and CSV are useful for piping into other tools:

```bash
mm accounts --format json | jq '.[].balance'
mm transactions --from 2026-01-01 --format csv > transactions.csv
mm analyze spending --format json | jq '.[] | select(.budget != null)'
```

## Development

```bash
uv sync --dev
uv run pytest
uv run ruff check .
```

## References

- [MoneyMoney AppleScript Documentation](https://moneymoney.app/applescript/)

## License

MIT
