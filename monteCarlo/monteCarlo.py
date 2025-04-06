import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime as dt
import yfinance as yf

def get_data(stocks,start,end):
    stockData = yf.download(stocks, start=start, end=end)['Close'].pct_change()
    meanReturns = stockData.mean()
    covMatrix = stockData.cov()
    return meanReturns, covMatrix

stockList= ["TSLA","AMD","NVDA","MSFT"]

endDate= dt.datetime.now()
startDate = endDate - dt.timedelta(days=365)

meanReturns, covMatrix = get_data(stockList,startDate,endDate)

weights = np.random.random(len(meanReturns))
weights /= np.sum(weights)

#monte Carlo Method
mc_sims = 10000 #number of simulation
T = 100

initialPortfolio = 10000

meanM = np.full(shape=(T,len(weights)), fill_value=meanReturns)
meanM = meanM.T

portfolio_sims = np.full(shape=(T,mc_sims),fill_value=0.0)

for m in range(0, mc_sims):
    Z = np.random.normal(size=(T,len(weights)))
    L = np.linalg.cholesky(covMatrix)
    dailyReturns = meanM + np.inner(L, Z)
    portfolio_sims[:,m] = np.cumprod(np.inner(weights,dailyReturns.T)+1)*initialPortfolio

def mcVaR(returns, alpha=5):
    """Innput: Pandas series of returns
       Output: percentile on return distribution to a given confidence level alpha """
    
    if isinstance(returns,pd.Series):
        return np.percentile(returns, alpha)
    else:
        raise TypeError("Expected a pandas data series")

def mcCVaR(returns, alpha=5):
    """Innput: Pandas series of returns
       Output: CVaR or Expected Shortfall to a given confidence level alpha """
    
    if isinstance(returns,pd.Series):
        belowVar = returns <= mcVaR(returns,alpha=alpha)
        return returns[belowVar].mean()
    else:
        raise TypeError("Expected a pandas data series")
    
portfolioResults = pd.Series(portfolio_sims[-1,:])

VaR = initialPortfolio - mcVaR(portfolioResults,alpha=5)
CVaR = initialPortfolio - mcCVaR(portfolioResults,alpha=5)

print("VaR ${}".format(round(VaR,2)))
print("CVaR ${}".format(round(CVaR,2)))

plt.plot(portfolio_sims)
plt.ylabel("Portfolio Value ($)")
plt.xlabel("Days")
plt.title("Monte Carlo simulation of a stock portfolio")
plt.show()
