import pandas as pd
import pandas_ta as ta
import statistics
import numpy as np
from pybit.unified_trading import HTTP
from keys import apiKey, apiSecret, coin_Market_Api
from time import sleep
import requests

#################################################
###############Conecting to Bybit################
#################################################
session = HTTP(api_key = apiKey, api_secret = apiSecret,recv_window=300000)

#Constans
timeframe = "D"
min_length = 20
rsi_lenght = 14
rsi_ema_lenght = 4
data_length = 90
token_list =  []
Candles = []
Benchmark = []


#Function for calculating alma_score
def alma_score(source, length, offset, sigma):
    source_df = pd.DataFrame(source)
    source_df.columns = ["Ratio"]
    alma = ta.alma(source_df["Ratio"],length,offset=offset,sigma=sigma).to_list()
    buy_signal = source[0] > float(alma[len(alma)-1])    
    score = 0
    if buy_signal:
        score = 1
    return score


#################################################
################ Prepering DATA #################
#################################################     
#Function for getting all symbols from bybit
def get_tickers():
    try:
        resp = session.get_tickers(category="linear")['result']['list']
        symbols = []
        for s in resp:
            if "USDT" in s['symbol'] and not 'USDC' in s['symbol']:
                symbols.append(s['symbol'])       
        return symbols
    except Exception as err:
        print(err)
        
#Function for getting candles data from symbol
def klines(symbol):
    try:
        resp = session.get_kline(
            categgory="linear",
            symbol=symbol,
            interval=timeframe,
            limit=data_length
        )['result']['list'] #tu spróbuj pobierać mniej danych
        resp = pd.DataFrame(resp)
        resp.columns= ['Time',' Open', 'High', 'Low', 'Close', 'Volume', 'Turnover']
        # resp = resp.set_index("Time")
        resp = resp.iloc[::-1]
        resp = resp.astype(float)
        close_price = resp["Close"].to_list()
        return close_price
    except Exception as err:
        print(err)

#function which erases all tokens with less than 20 day chart history 
def cleaning_data():
    symbols = get_tickers()   
    for s in symbols:
        close = klines(s)
        if len(close) >= min_length:
            token_list.append(s)

          
#Function for creating 2D matrix with tokens and prices
def creating_matrix(symbols):
    for i in range(len(symbols)):
        row = []
        Candles.append(row)
    j = 0
    for i in range(len(symbols)):
        close_price = klines(symbols[i])
        for row in close_price:
            Candles[i].append(row)
        if symbols[i] == "BTCUSDT" or symbols[i] == "ETHUSDT":
            r = []
            Benchmark.append(r)
            for row in close_price:
                Benchmark[j].append(row)
            j+=1 


#################################################
################### Tournament ##################
#################################################
  
#Function for outperformance ratio
def calculating_ratios():
    outperformance = []
    for i in range(len(token_list)):
        outperformance.append(0)
        for j in range(len(token_list)):
            if(i==j):
                continue
            ratios=[]
            for k in range(len(Candles[i])):
                if k >= len(Candles[j]):
                    break
                ratios.append(Candles[i][k]/Candles[j][k])
            score = alma_score(ratios,min_length, 0.3, 3)
            outperformance[i]+=score
    median = statistics.median(outperformance)
    
    i = 0
    while i < len(token_list):
        if  outperformance[i] < median:
            token_list.pop(i)
            Candles.pop(i)
            outperformance.pop(i)          
        else:
            i+=1
            
#function for calculating RSI
def rsi_tournament():
    i = 0
    while i < len(token_list):
        price_df = pd.DataFrame(Candles[i])
        price_df.columns= ["Price"]
        rsi_before_ema = ta.rsi(price_df["Price"],rsi_lenght)
        rsi_after_ema = ta.ema(rsi_before_ema,rsi_ema_lenght).to_list()
        if rsi_after_ema[len(rsi_after_ema)-1] < 50:
            token_list.pop(i)
            Candles.pop(i)      
        else:
            i+=1
            

#function for calculating Beta
def beta_calculation():
    beta_table = []
    for i in range(len(token_list)):
        asset_data = pd.DataFrame(Candles[i])
        asset_data.columns = ['Returns']
        asset_data['Returns'] = asset_data['Returns'].pct_change()
        asset_data.dropna(inplace=True)
        row = []
        beta_table.append(row)
        
        for bench in Benchmark:
            bench_data = pd.DataFrame(bench)
            bench_data.columns = ["Returns"]
            bench_data['Returns'] = bench_data['Returns'].pct_change()
            bench_data.dropna(inplace=True)
            return_data = pd.merge(asset_data['Returns'], bench_data['Returns'], how='inner', left_index=True, right_index=True, suffixes=('_asset', '_benchmark'))
            covariance = return_data.cov().iloc[0,1]
            variance = return_data.var().iloc[1]
            beta = covariance/ variance
            beta_table[i].append(beta)

    beta_df = pd.DataFrame(beta_table, columns=["BTC", "ETH"])
    beta_median_BTC = beta_df["BTC"].median()
    beta_median_ETH = beta_df["ETH"].median()
    
    i = 0
    while i < len(token_list):
        if beta_table[i][0] < beta_median_BTC or beta_table[i][1] < beta_median_ETH:
            token_list.pop(i)
            Candles.pop(i)
            beta_table.pop(i)         
        else:
            i+=1
    
#Function for calculating best Sortino ratio
def sortino_turnament():
    sortino_table = []
    for i in range(len(token_list)):
        rf = 0.01/365
        tradingDays = 90
        price_df = pd.DataFrame(Candles[i])
        log_returns = np.log(price_df[0]/price_df[0].shift(1)).dropna()
        sortino_vol = log_returns[log_returns<0].rolling(window=tradingDays, center=True, min_periods=10).std()*np.sqrt(tradingDays)
        sortino_ratio = (log_returns.rolling(window=tradingDays).mean() - rf)*tradingDays/sortino_vol
        sortino_table.append(sortino_ratio)
        
    sortino_median = statistics.median(sortino_table)
    
    i = 0
    while i < len(token_list):
        if sortino_table[i] < sortino_median:
            token_list.pop(i)
            Candles.pop(i)
            sortino_table.pop(i)          
        else:
            i+=1

#Function for geting tokens marketcap
def mc_tournament():
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': coin_Market_Api,
    }
    mc_list = []
    j = 0
    i = 0
    while i < len(token_list):
        t= token_list[i]
        if j == 10:
            j=0
            sleep(60)
        ticker = ''
        k = len(t) - 5
        while (ord(t[k]) >= 65 or ord(t[k]) == 49) and k >= 0:
            ticker += t[k]
            k-=1
        
        ticker = ticker[::-1]
        
        parameters = {
            'symbol': ticker,
            'convert': 'USD'
        }

        response = requests.get(url, headers=headers, params=parameters)
        data = response.json()

        if response.status_code == 200:
            try:
                market_cap = data['data'][ticker]['quote']['USD']['market_cap']
                mc_list.append(market_cap)
                i+=1
            except KeyError:
                # print(f"Market cap for {ticker} not found.")
                token_list.pop(i)
                Candles.pop(i)
        else:
            # print(f"Error {response.status_code}: {data['status']['error_message']}")
            token_list.pop(i)
            Candles.pop(i)
        j+=1
    m_median = statistics.median(mc_list)
    i = 0
    while i < len(token_list):
        if mc_list[i] > m_median:
            token_list.pop(i)
            Candles.pop(i)
            mc_list.pop(i)          
        else:
            i+=1
    
#################################################  ``
#############Startinng function##################
#################################################  
def start_tournament():
    print("---------------- CLEANING DATA ----------------")
    cleaning_data()
    print("---------------- CREATING MATRIX ----------------")
    creating_matrix(token_list)
    # print("---------------- SORRTINO TOURNAMENT ----------------")
    # sortino_turnament()
    print("---------------- RSI TOURNAMENT ----------------")
    rsi_tournament()
    print("---------------- BETA CALCULATION ----------------")
    beta_calculation()
    print("---------------- MARKETCAP TOURNAMENNT ----------------")
    mc_tournament()
    print("---------------- CALCULATING RATIOS ----------------")
    calculating_ratios()
    print("---------------- CALCULATING RATIOS 2 ----------------")
    calculating_ratios()
    
    
#################################################  
#############REBALANCING function################
#################################################  
def set_mode(symbol):
    try:
        resp = session.switch_margin_mode(category="linear",symbol=symbol,tradeMode=1,buyLeverage='1',sellLeverage='1')
    except:
        x=10
        
def get_precision(symbol):
    try:
        resp = session.get_instruments_info(category="linear",symbol=symbol)['result']['list'][0]
        qty = resp['lotSizeFilter']['qtyStep']
        
        if '.' in qty:
            qty = len(qty.split('.')[1])
        else:
            qty = 0
        return qty       
    except Exception as err:
        print(err)

#Function for rebalancing current position
def rebalancing_current_pos(symbol,orderType,positionVal,target_alocations,mark_price):
    diff = np.abs(positionVal-target_alocations)
    Qty = round(diff/mark_price,get_precision(symbol))
    if Qty*mark_price>5:
        set_mode(symbol)
        session.place_order(category="linear",symbol=symbol,
                                    side=orderType, orderType='Market',qty=Qty,reduce_only=False)
    

#Function for rebalancing portfolio
def rebalancing(t_list):
    try:
        total_balance = float(session.get_wallet_balance(accountType="CONTRACT",coin="USDT")["result"]['list'][0]["coin"][0]['walletBalance'])
        new_alocations = np.floor(total_balance/len(t_list))
        curent_open_pos = pd.DataFrame(session.get_positions(category="linear",settleCoin="USDT")['result']['list'])
        curent_open_pos = curent_open_pos[['symbol','positionValue','size','markPrice']]
        curent_open_pos['markPrice'] = curent_open_pos['markPrice'].astype('float64')
        
        #selling all tokens that aren't on token list
        for i in range(len(curent_open_pos['size'])):
            if curent_open_pos['symbol'][i] not in t_list:
                set_mode(curent_open_pos['symbol'][i])
                session.place_order(category="linear",symbol=curent_open_pos['symbol'][i],
                                    side='Sell', orderType='Market',qty=curent_open_pos['size'][i],reduce_only=True)
                print("___________________________")
                print("| SELLING TOKEN - {} |".format(curent_open_pos['symbol'][i]))
                print("___________________________")
                
        #rebalancing all currently open position        
        for i in range(len(curent_open_pos['size'])):
            if curent_open_pos['symbol'][i] in t_list and float(curent_open_pos['positionValue'][i]) > new_alocations:
                rebalancing_current_pos(str(curent_open_pos['symbol'][i]),"Sell",float(curent_open_pos['positionValue'][i]),new_alocations,float(curent_open_pos['markPrice'][i]))
                print("___________________________")
                print("| SELLING TOKEN - {} |".format(curent_open_pos['symbol'][i]))
                print("___________________________")
                              
            elif curent_open_pos['symbol'][i] in t_list and float(curent_open_pos['positionValue'][i]) < new_alocations:
                rebalancing_current_pos(str(curent_open_pos['symbol'][i]),"Buy",float(curent_open_pos['positionValue'][i]),new_alocations,float(curent_open_pos['markPrice'][i]))
                print("___________________________")
                print("| BUYING TOKEN - {} |".format(curent_open_pos['symbol'][i]))
                print("___________________________")
                
        #buying new positions
        for t in t_list:
            if t not in curent_open_pos['symbol'].to_list():
                mark_price = session.get_tickers(category='linear',symbol=t)['result']['list'][0]['markPrice']
                rebalancing_current_pos(t,'Buy',0,new_alocations,float(mark_price))
                print("___________________________")
                print("| BUYING TOKEN - {} |".format(t))
                print("___________________________")
                                 
    except Exception as err:
        print(err)          
        

#################################################  
############# AUTO RSPS function ################
#################################################     


print("---------------- STARTING ----------------")
start_tournament()

print("Tournaments Winners:")
for e in token_list:
    print("Token Symbol: {}".format(e))
    
print("---------------- STARTING REBALANCING ----------------")

# if len(token_list) > 0:
#     rebalancing(token_list)
    
# else:
#     token_list = ["BTCUSDT","ETHUSDT"]
#     rebalancing(token_list)
    
print("---------------- FINISHED REBALANCING ----------------")