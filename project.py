import pandas as pd
import numpy as np
import yfinance as yf

TICKERS = ['EQQQ.L', 'SGLN.L', 'IDTG.L', 'GLTL.L', 'ISF.L', 'CORN.L']

def get_data():
    px = yf.download(
        TICKERS + ['GBPUSD=X'],
        start='2015-01-01',
        end='2026-08-01',
        interval='1d',
        auto_adjust=True,       
        group_by='column',
        multi_level_index=False, 
        progress=False,

    )['Close']
    fx = px.pop('GBPUSD=X')
    px = px.dropna(how='all') 
    return px, fx.reindex(px.index).ffill()

def ewmac_forecast(price, fast, slow, scalar, cap=20):
    raw = price.ewm(span=fast).mean() - price.ewm(span=slow).mean()
    vol = daily_vol(price)
    return (scalar * raw / vol).clip(-cap, cap)

def daily_vol(price, span=32, min_periods=10):
    sigma = price.diff().ewm(span=span, min_periods=min_periods).std()
    floor = sigma.expanding(min_periods=252).quantile(0.05)
    return sigma.clip(lower=floor)

def gbp_factor(price, fx_rate, currency):
    fx_rate = fx_rate.reindex(price.index).ffill()
    cols = {}
    for t in price.columns:
        c = currency[t]
        if c == 'GBP': cols[t] = pd.Series(1.0, index=price.index)
        elif c == 'GBp': cols[t] = pd.Series(0.01, index=price.index)   
        elif c == 'USD': cols[t] = 1.0 / fx_rate 
        else: 
            raise ValueError(f'{t}: unhandled currency {c!r}')
    return pd.DataFrame(cols) 

def diversification_multiplier(corr, weights, cap=2.5):
    corr = corr.clip(lower=0.0)
    w = weights.reindex(corr.index)
    assert w.notna().all(), f"missing weights for {list(w.index[w.isna()])}"
    w = w / w.sum()
    return min(cap, 1.0 / np.sqrt(w @ corr @ w))

def instrument_diversification_multiplier(subsys_ret, weights, min_periods=504, cap=2.5):
    out = pd.Series(index=subsys_ret.index, dtype=float)
    for i, dt in enumerate(subsys_ret.index):
        window = subsys_ret.iloc[:i + 1]
        live = window.columns[window.notna().sum() >= min_periods]
        if len(live) < 2:
            out.loc[dt] = 1.0
            continue
        corr = window[live].corr().clip(lower=0.0)     
        w = weights[live] / weights[live].sum()   
        out.loc[dt] = diversification_multiplier(corr, w) 

    return out.ffill()

def forecast_diversification_multiplier(variants, weights=None, cap=2.5):
    stacked = pd.DataFrame({k: v.stack() for k, v in variants.items()}).dropna()
    corr = stacked.corr()

    if weights is None:
        weights = pd.Series(1 / len(variants), index=corr.index)

    return diversification_multiplier(corr, weights, cap), corr

 
def fetch_costs_ibkr(tickers, currency, host='127.0.0.1', port=4002,
                     client_id=0, exchange='LSE', order_size=100,
                     samples=3, wait=3.0, market_data_type=1):
    
    from ib_async import IB, Stock, MarketOrder
 
    ib = IB()
    ib.connect(host, port, clientId=client_id)
    ib.reqMarketDataType(market_data_type)
 
    rows = {}
    try:
        for t in tickers:
            symbol = t.split('.')[0]
            ccy = currency[t]
            ib_ccy = 'GBP' if ccy in ('GBP', 'GBp') else ccy
            scale = 0.01 if ccy == 'GBp' else 1.0
 
            contract = Stock(symbol, 'SMART', ib_ccy, primaryExchange=exchange)
            ib.qualifyContracts(contract)

            if not contract.conId:
                contract = Stock(symbol, exchange, ib_ccy)
                ib.qualifyContracts(contract)

            if not contract.conId:
                rows[t] = dict.fromkeys(
                    ['bid', 'ask', 'mid', 'half_spread_bp',
                     'commission', 'commission_bp', 'total_bp'], np.nan)
                continue
 
            quotes = []
            tick = ib.reqMktData(contract, '', False, False)
            for _ in range(samples):
                ib.sleep(wait)
                bid, ask = tick.bid, tick.ask
                if bid and ask and bid > 0 and ask > 0 and ask > bid:
                    quotes.append((bid, ask))
            ib.cancelMktData(contract)
 
            if not quotes:
                rows[t] = dict.fromkeys(
                    ['bid', 'ask', 'mid', 'half_spread_bp',
                     'commission', 'commission_bp', 'total_bp'], np.nan)
                continue
 
            bid = float(np.median([q[0] for q in quotes]))
            ask = float(np.median([q[1] for q in quotes]))
            mid = (bid + ask) / 2
            half_spread_bp = (ask - bid) / mid * 10_000 / 2
 
            try:
                state = ib.whatIfOrder(contract, MarketOrder('BUY', order_size))
                if isinstance(state, list):
                    state = state[0]
                commission = float(state.commission)
                notional = mid * order_size * scale
                commission_bp = commission / notional * 10_000
            except Exception as e:
                print(f'{t}: whatIfOrder failed - {e}')
                commission, commission_bp = np.nan, np.nan
 
            rows[t] = {
                'bid': bid,
                'ask': ask,
                'mid': mid,
                'half_spread_bp': half_spread_bp,
                'commission': commission,
                'commission_bp': commission_bp,
                'total_bp': half_spread_bp + (commission_bp if commission_bp == commission_bp else 0.0),
            }
    finally:
        ib.disconnect()
 
    return pd.DataFrame(rows).T

def run_backtest(optimal, avg_position, prices,
                 buffer_frac=0.10, cost_bp=None, capital=1_000_000):
    if not optimal.columns.equals(prices.columns):
        raise ValueError('optimal and prices must share columns')
 
    buf = (buffer_frac * avg_position).abs()
    lower = (optimal - buf).round()
    upper = (optimal + buf).round()
 
    lo = lower.to_numpy()
    up = upper.to_numpy()
    n_days, n_inst = lo.shape
 
    positions = np.zeros((n_days, n_inst))
    trades = np.zeros((n_days, n_inst))
    held = np.zeros(n_inst)
 
    for i in range(n_days):
        target = np.clip(held, lo[i], up[i])
        target = np.where(np.isnan(target), 0.0, target)
        trades[i] = target - held
        held = target
        positions[i] = held
 
    positions = pd.DataFrame(positions, index=optimal.index, columns=optimal.columns)
    trades = pd.DataFrame(trades, index=optimal.index, columns=optimal.columns)
 
    gross = (positions.shift(1) * prices.diff()).sum(axis=1)
    notional_traded = trades.abs() * prices
 
    if cost_bp is None:
        costs = pd.Series(0.0, index=positions.index)
    else:
        costs = notional_traded.mul(cost_bp, axis=1).sum(axis=1) / 10_000
 
    return {
        'positions': positions,
        'trades': trades,
        'notional_traded': notional_traded,
        'gross': gross,
        'costs': costs,
        'net': gross - costs,
    }
 
 
def summarise(pnl, notional_traded=None, capital=1_000_000):
    TRADING_DAYS = 256
    pnl = pnl.dropna()
    years = len(pnl) / TRADING_DAYS
    equity = capital + pnl.cumsum()
 
    out = {
        'total_pnl': pnl.sum(),
        'ann_return': pnl.mean() * TRADING_DAYS / capital,
        'ann_vol': pnl.std() * np.sqrt(TRADING_DAYS) / capital,
        'sharpe': pnl.mean() / pnl.std() * np.sqrt(TRADING_DAYS),
        'max_dd': (equity / equity.cummax() - 1).min(),
        'worst_day': (pnl / capital).min(),
        'years': years,
    }
    if notional_traded is not None:
        out['turnover'] = notional_traded.sum().sum() / capital / years
    return out

def plot_equity_curve(pnl, gross_pnl=None, capital=1_000_000,
                      title='EWMAC portfolio', path='equity_curve.png'):
    import matplotlib.pyplot as plt

    pnl = pnl.dropna()
    equity = capital + pnl.cumsum()
    dd = equity / equity.cummax() - 1
    trough = dd.idxmin()
    peak = equity.loc[:trough].idxmax()

    fig, (ax_eq, ax_dd) = plt.subplots(
        2, 1, sharex=True, figsize=(11, 7),
        gridspec_kw={'height_ratios': [3, 1]})

    if gross_pnl is not None:
        gross_equity = capital + gross_pnl.reindex(pnl.index).dropna().cumsum()
        ax_eq.plot(gross_equity.index, gross_equity / 1e6,
                   lw=1.0, color='0.65', label='gross')

    ax_eq.plot(equity.index, equity / 1e6, lw=1.3, color='tab:blue', label='net')
    ax_eq.axhline(capital / 1e6, lw=0.8, color='k', ls='--')
    ax_eq.axvspan(peak, trough, color='tab:red', alpha=0.10)
    ax_eq.set_ylabel('equity (GBP m)')
    ax_eq.set_title(f'{title}    sharpe {pnl.mean() / pnl.std() * np.sqrt(256):.2f}'
                    f'    max dd {dd.min():.1%}')
    ax_eq.legend(loc='upper left', frameon=False)
    ax_eq.grid(alpha=0.3)

    ax_dd.fill_between(dd.index, dd * 100, 0, color='tab:red', alpha=0.4, lw=0)
    ax_dd.set_ylabel('drawdown (%)')
    ax_dd.grid(alpha=0.3)

    fig.tight_layout()
    if path is None:
        plt.show()
    else:
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print(f'\nsaved        {path}')
    return fig


def main():
    df, fx = get_data()
    currency = {t: yf.Ticker(t).fast_info['currency'] for t in TICKERS} 
    adj = gbp_factor(df, fx, currency)
    refined_df = df * adj 
 
    variants = {'16/64': ewmac_forecast(df, 16, 64, scalar=4.10),
                '32/128': ewmac_forecast(df, 32, 128, scalar=2.79),
                '64/256': ewmac_forecast(df, 64, 256, scalar=1.91)}
    fdm, _ = forecast_diversification_multiplier(variants)
    forecast = (sum(variants.values()) / len(variants)*fdm).clip(-20,20)

    price_vol = daily_vol(refined_df)
    vol_scalar = (1000000 * 0.2 / 16) / price_vol              
    subsystem_position = vol_scalar * forecast / 10
    subsystem_return = subsystem_position.shift(1) * refined_df.diff()

    live = refined_df.notna()
    weights = live.div(live.sum(axis=1), axis=0)
    idm = instrument_diversification_multiplier(subsystem_return, pd.Series(1/6, index=refined_df.columns))

    costs = pd.Series({'EQQQ.L': 1.10, 'SGLN.L': 2.38, 'IDTG.L': 8.94, 'GLTL.L': 6.15, 'ISF.L': 0.95, 'CORN.L': 6.68,}) + 5.0 
    optimal = subsystem_position.mul(weights, axis=1).mul(idm, axis=0)
    avg_position = vol_scalar.mul(weights, axis=1).mul(idm, axis=0)
    start = live.sum(axis=1).ge(3).idxmax()

    result = run_backtest(optimal.loc[start:], avg_position.loc[start:],
                        refined_df.loc[start:],
                        buffer_frac=0.10, cost_bp=costs)
    net = summarise(result['net'], result['notional_traded'])
    gross = summarise(result['gross'], result['notional_traded'])

    print(f"\nyears        {net['years']:>12.2f}")
    print(f"turnover     {net['turnover']:>12.1f}x")
    print(f"ann vol      {net['ann_vol']:>12.2%}")
    print(f"ann return   {net['ann_return']:>12.2%}")
    print(f"max drawdown {net['max_dd']:>12.2%}")
    print(f"sharpe gross {gross['sharpe']:>12.3f}")
    print(f"sharpe net   {net['sharpe']:>12.3f}")
    print(f"cost drag    {gross['sharpe'] - net['sharpe']:>12.3f}")

    equity = 1_000_000 + result['net'].cumsum()
    dd = equity / equity.cummax() - 1
    trough = dd.idxmin()
    peak = equity.loc[:trough].idxmax()
    after = equity.loc[trough:]
    rec = after[after >= equity.loc[peak]]
    print(f"\ndrawdown     {peak.date()} -> {trough.date()} ({dd.min():.1%})")
    print(f"recovered    {rec.index[0].date() if len(rec) else 'NOT YET'}")

    plot_equity_curve(result['net'], gross_pnl=result['gross'])

if __name__ == '__main__':
    main()