# EWMAC Trend-Following Model

This is a systematic trend-following system across six LSE-listed equity, commodity and bond ETFs. It follows the framework in Robert Carver's *Systematic Trading*.

## Results (11.4 years)

| | |
|---|---|
| Gross Sharpe | 0.48 |
| Net Sharpe (after costs) | 0.38 |
| Annual return | 7.4% |
| Realised volatility | 19.2% (target 20%) |
| Maximum drawdown | 42.9% (Mar 2017 – Mar 2019, recovered May 2020: 3.2 years from peak to recovery) |
| Turnover | 22× |

The account spent over three years below its March 2017 peak. Even with a consistent edge over the last six years, 11 years isn't a long enough sample to prove the model is viable.

## Method

- **Forecasts:** three EWMAC speeds (16/64, 32/128, 64/256), each scaled to an average absolute forecast of 10 and capped at ±20.
  - The three are blended with a forecast diversification multiplier.
- **Position sizing:** each instrument is volatility-targeted to a 20% annual target on £1,000,000.
  - The instruments are combined with an expanding-window instrument diversification multiplier, so the multiplier on each date uses only data available on that date.
- **Buffering:** a 10% position buffer creates a no-trade band. This keeps turnover to 22× and trading costs realistic, rather than assuming continuous rebalancing.
- **Costs:** per-instrument spread costs sampled from the IBKR API, plus a flat 5 bp per trade.
- **No in-sample fitting:**
  - Forecast scalars, the cap and the buffer width all come from Carver rather than being optimised on this data.
  - That means the results aren't a product of parameter search.
  - It also means the system isn't tuned to this instrument set.

## Running

```bash
python EWMAC_project.py
```

Prices are downloaded from Yahoo Finance (`yfinance`) for Jan 2015 – Aug 2026. The script prints the summary statistics and saves `equity_curve.png`. `fetch_costs_ibkr()` shows how the spreads were sampled, but it needs a running IB Gateway and isn't called by default.
