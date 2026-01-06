# mm-cli

CLI tool for [MoneyMoney](https://moneymoney-app.com/) macOS app - retrieve accounts, transactions, categories and manage categorization via AppleScript.

## Features

- List accounts and balances
- Query transactions with filtering
- Export and manage categories
- Analyze category usage
- Update transaction categories
- Create bank transfers and direct debits
- Manage securities portfolio

## Requirements

- macOS (required for AppleScript)
- MoneyMoney app installed
- Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/mm-cli.git
cd mm-cli

# Install with uv
uv sync
```

## Usage

```bash
# List all accounts
mm accounts

# List transactions
mm transactions --from 2024-01-01 --to 2024-12-31

# Show categories
mm categories

# Show category usage statistics
mm category-usage

# Update transaction category
mm set-category <transaction-id> <category-name>
```

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linting
uv run ruff check .
```

## References

- [MoneyMoney AppleScript Documentation](https://moneymoney.app/applescript/)
- Inspired by [moneymoney-cli](https://github.com/dobernhardt/moneymoney-cli)

## License

MIT
