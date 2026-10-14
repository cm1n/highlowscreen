# High-Low Screen

An autonomous, company-use daily market scanner. It identifies large-cap stocks making three-month or 52-week highs and lows across the US, Japan, Taiwan, Hong Kong, and China A-share markets. The legacy fallback retains its 60-trading-session screening rule and labels it separately.

New-low rows show sortable declines from the three-month and 52-week intraday highs: `(as-of close / period high - 1) * 100`. Each new scan stores the reference highs, percentages, price date, and source. Historical rows without a stored price snapshot display an em dash; current highs are never substituted into earlier dates.

## Scope

- Run the scan, publish the dashboard, and retain its daily output history.
- Produce reproducible market data, screen results, and concise market commentary.
- Keep all company automation contained in this repository.

This repository does not contain personal portfolios, research notes, investment theses, or FinanceVault data. It does not write candidates into FinanceVault.

## Operation

GitHub Actions runs `.github/workflows/daily-scan.yml` at 08:00 KST. The workflow executes:

```bash
python tools/high_low_scan.py --out-dir .
```

It then adds commentary when available, rebuilds the dashboard, and commits the daily outputs.

## Outputs

- `index.html`: interactive daily dashboard
- `scan_YYYYMMDD.csv`: high/low screen results
- `sector_`, `etf_`, and `index_` CSVs: market and sector context
- `top_movers_YYYYMMDD.json`: candidates for commentary
- `신고신저가_YYYYMMDD.xlsx`: downloadable workbook

## Boundary with FinanceVault

FinanceVault is a separate, private personal-research environment. A result from this scanner may be reviewed there manually, but there is no automated data transfer or shared runtime dependency.
