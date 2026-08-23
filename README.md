EWMAC Trend-Following Model

A systematic trend-following system across six LSE-listed equity, commodity and bond ETFs, following the framework in Robert Carver's Systematic Trading.

Over 11.4 years: gross Sharpe 0.48, net 0.39 after spreads sampled from the IBKR API. Realised volatility 19.2% against a 20% target. Maximum drawdown 42.9%, with 3.2 years from peak to recovery. With 3 years of negative
balance even with a consistent edge over the past 6 years is not a long enough time frame to prove the viability of the model.

Three EWMAC speeds are blended and scaled by a forecast diversification multiplier, then combined across instruments with an expanding-window instrument diversification multiplier — expanding rather than full-sample so the 
multiplier at each date uses only data available at that date. Position buffering at 10% of the target creates a no-trade band, holding turnover to 22× and keeping trading costs realistic rather than assuming continuous 
rebalancing.

No in-sample fitting: forecast scalars, cap, and buffer width are all taken from Carver rather than optimised on this data. That is deliberate — it means the results are not a product of parameter search — but it also means 
the system is not tuned to this instrument set.

