# EWMAC TRADING STRATEGY BACKTESTER 
#### https://youtu.be/9W8-N21kN6A
#### Description:
This project executes a systematic trading strategy using an exponentially weighted moving average crossover (EWMAC)

To get an EWMAC you first need EWMA which is calculated by giving more weight to more recent days of price movement. let A = 2/(T+1) which is the decay parameter to give less weight to less recent price movements for T=32 day moving average at time t: EWMA_t = A * P_t + (1-A) * EWMA_(t-1). This is very easily done by calling .ewm(span=T) then the .mean() outputs a dataframe of a rolling mean on a 32 day basis.

Then the slow moving average is taken away from the fast moving average to get a raw forecast, if the forecast is positive it suggests a recent bullish trend, and vice versa for a negative value.

Next to calculate is the assets price volatility (standard deviation of daily price change over the given time period) I use another EWMA for this because it decays old price values more efficiently than giving equal weight to all days within the window, for example if there is a large price move (5-10%) 31 days ago in a 32 day window then the simple standard deviation of price returns will be much higher than the EWMA of price returns, so it is better to use exponential weighting so that outliers carry less weight as time goes on.

Finally the forecast returns the difference in EWMA multiplied by the scalar value which is a fixed number that scales up the forecast so that  crossovers get the same scalar weight as slower ones, this value is then divided by the price volatilfasterity, .clip(-cap, cap) then caps the forecast at +-20, this is a concept from Robert Carver's Systematic Trading so that when there are massively skewed forecasts the trading system does not take on massive positions. for the strategy I took the average of 3 differnet EWMAC values then took the mean and multipled by the fdm to get my forecast value.

Working chronologically through the document:

get_data is self explanatory, it uses yfinance to request the data of the tickers in TICKERS as well as the GBPUSD exhange rate, because some of the assets I requested are priced in pence and dollars rather than British Pounds, which flows into gbp_factor which reads the currency of each of the assets and writes a new dataframe with the adjusted price changes which is needed so that all calculations can be accurate.

I will group instrument and forecast diversification multipler together in explanation because they are the same process for 2 different reasons. Firstly instrument diversification multiplier is to make sure the target volatility of my system is consistent, since because I have a basket of uncorrelated assets such as equities and commodities, they offset risk and so I need to scale up the positions in my portfolio so that I can reach my target annual volatility of 20% on a simulated £1000000 trading account, the function returns a series of values that are used on a rolling basis to keep volatility constant near 20%.

Forecast diversification multiplier is the same concept but the diversification is across strategy variants, like I said above I used the mean of 3 different variants of the EWMAC to get a forecast value, specifically 16/64, 32/128 and 64/256 (the factor of 4 is a tennet of Carver's systematic trading EWMAC strategy) which returns another scalar value to multiply the portfolio by to achieve the risk target.

Now the 3 important functions

fetch_costs_ibkr uses interactive brokers local API hosted on my computer to request live market data to calculate the spread costs of trading each asset in TICKERS which returns a dataframe that specifics the bid, ask, midprice, half spread bp, commision, commision bp and total bp (bp=basis point where 1bp = 0.01%) after implimenting this I realised that it makes the code run REALLY slowly, so I ran it and saved the dictionary of costs so that I wouldn't have to keep calling the API

Next was for me the most complicated function in terms of theory and application is the actual backtest, the system trades based on the scalar value that is returned by the ewmac_forecast function but this function is called every day, and if the system were to trade 6 assets every day that would be 6 trades executed every day which 1536 trades a year and would eat up all my hypothetical gains in trading costs, for that reason I wanted to set a 10% change parameter as suggested by Carver which takes 10% of the average position of the asset and when the held position leaves the current band, the system trades to the nearest edge, not back to optimal. Trading to optimal would leave you centred in the band and equally likely to breach again the next day; stopping at the edge does the minimum required and materially reduces turnover for the same signal.

Then summarise and report return all the interesting numbers that you want to know from a trading strategy.

inside the main function the blocks of code do the following:

1. fetches the data and adjusts the dataframe for fx rates

2. calculates the forecast using variants and forecast diversification multiplier capped at +-20

3. calculates the price volatility and the volatility scalar to calculate portfolio positions and returns

4. calculates weights based on whether or not the instruments were trading, I want equal weights but IDTG ticker was only available from 2020 so each asset is weighted equal as 1/5 until 2020 where they are weighted at 1/6, calculated each day until IDTG started trading

5. turns forecasts into share counts. positions are sized as if each asset were the whole book, then scaled down by weights and back up by the IDM. avg_position is the same thing at forecast=10, used only to set the buffer width — it has to be a fixed share count or the band shrinks to zero when the forecast crosses zero.

6. runs the backtest. start is the first day 3+ assets have prices. the loop can't be vectorised because whether you trade today depends on what you're holding, which depends on yesterday. costs are half the spread plus 5bp commission on the notional traded.

7. reports results. summarise returns a dict, printing is separate so sweeps don't spam output. called on gross and net, the difference is the cost drag — Carver says keep it under 0.13.
