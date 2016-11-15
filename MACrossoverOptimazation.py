"""Optimal MA crossover strategy testing including dividends."""
import pandas_datareader.data as web
import pandas as pd
import datetime
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm
from matplotlib.ticker import LinearLocator, FormatStrFormatter
import matplotlib.pyplot as plt
import numpy as np
import xlsxwriter
import time
import os
import sys
# User created modules
import MACrossoverFunctions as macf
import YahooDataReader as ydr

"""It should do the following:
    1) Create 40 different Exponential Moving Average ( from 5 to 200 with
       step size = 5)
    2) For each ema-pair compute total portfolio value and total cost
    3) Try to see if there is any dividend-data for the stock.
       Iterate through this and for each dividend-date find total dividend
       for that date and sum this up to a total
    4) Add the total dividends and total portfoliovalue and from the
       formula (total sharevalue + total dividend - total cost ) / total cost
               * 100 %
    5) This gain should be added for the EMA-pair and be written to excel
    3) As a clean-up summarize a total in # of stocks, total value and total
       dividend value paid.

"""
# Parametersection
start_MA = 50
end_MA = 200
gridSize = 30
debug = False

stock = "T"
start = datetime.datetime(2006, 1, 1)
end = datetime.datetime(2022, 1, 27)
print('****** Create Workbook ******')
excelOutfile = 'OptimizeMACrossOverData.xlsx'
# Test if excelOutfile exists, remove and create new one
if os.path.isfile(excelOutfile):
    os.remove(excelOutfile)
workbook = xlsxwriter.Workbook(excelOutfile)
row = 0
col = 0
Z = np.zeros(shape=(gridSize + 1,gridSize+ 1))
min_gain = 1000
max_gain = 0
min_tot_portfolio = 0
max_tot_portfolio = 0
min_max_ma = 0
min_min_ma = 0
max_max_ma = 0
max_min_ma = 0
# Add worksheet for result data
print('****** Create Worksheets to workbook ******')
# Create worksheet for trades
worksheet = workbook.add_worksheet('CrossoverData')
# Add headers to worksheet should add on horizontal and vertical
for i in range(1, (gridSize+1)):
    worksheet.write(i, 0, str(i*5+45))
    worksheet.write(0, i, str(i*5+45))

# Headers for the table is generated
# Now read the shareprice data
print("Testing stock %s " % (stock))
try:
    f = web.DataReader(stock, 'yahoo', start, end)
    if debug:
        print(list(f.columns.values))
    print('****** Create Moving Average Data ******')
    closeList = pd.Series(f['Adj Close'])
    emaList = []
    for i in range(1, gridSize+1):
        ema = pd.ewma(f['Adj Close'], span=(i*5 +45))
        ema.columns = "%i" % (i*5+45)
        emaList.append(ema)
    print("****** Done creating Moving Average Data ******")
    if debug:
        print("Size of array is: %i" % (len(emaList)))
        print("Size of test is: %i" % (len(emaList[1])))
        print("Size of test is: %i" % (len(f['Adj Close'])))
        print(emaList[1])
        print(emaList[3])
        print("emaList[1][2826] is %f" % (emaList[1][2826]))
        print("emaList[3][2826] is %f" % (emaList[3][2826]))

    # Fetch the dividend data and sort it in correct order
    # Now fetch all dividend data for the given stock
    dividendData = ydr.yahooFinanceDataReader([stock],
                                              [1, 1, 2000, 31, 12, 2020], [],
                                              "dividend")


    # Now all the required data is aqquired for doing the tests.

    for i in range(0, gridSize):
        for j in range(0, gridSize):
            tradingData = macf.computeMACrossOver(closeList, emaList[i], emaList[j])
            ant = len(tradingData) - 1
            totPortfolioValue = 0
            totInvestmentCost = 0
            totDividends = 0
            gain = 0
            if tradingData:
                totPortfolioValue = float(tradingData[ant][5]) *    float(closeList[len(closeList)-1])
                totInvestmentCost = float(tradingData[ant][4])
                # Find how much in dividend also adds to gain
                # Sort the data such that the dividends are from start to end
                if dividendData:
                    dividendData.sort(key=lambda x: x[0])
                    for a in range(0, len(tradingData)):
                        fromElement = tradingData[a]
                        fromDate = int(fromElement[1])
                        if a < len(tradingData) - 1:
                            toElement = tradingData[a+1]
                            toDate = int(toElement[1])
                        else:
                            toDate = 22001231

                        for item in dividendData:
                            divDate = int(item[0].replace("-", ""))
                            if divDate-14 > fromDate and divDate-14 < toDate:
                                # Do have a dividend for the amount in fromElement
                                divAmount = float(fromElement[5]) * float(item[1])
                                totDividends = totDividends + divAmount

                gain = (totPortfolioValue + totDividends - totInvestmentCost ) * 100/ totInvestmentCost
                # gain = totDividends/totInvestmentCost
            if min_gain > gain:
                min_gain = gain
                # min_tot_portfolio = float(tradingData[ant][5])
                min_min_ma = 45 + 5 * i
                min_max_ma = 45 + 5 * j
            if max_gain < gain:
                max_gain = gain
                # max_tot_portfolio = float(tradingData[ant][5])
                max_min_ma = 45 + 5 * i
                max_max_ma = 45 + 5 * j
            if debug:
                # print("Portfolio size is: %i and total invested is: %f"
                #       % (tradingData[ant][5], tradingData[ant][4]))
                print("Find how much value today:")
                print("Last value is: %f" % (closeList[len(closeList)-1]))
                print("Tot portfolio value is %f" % (totPortfolioValue))
                print("Total dividends are %f" % (totDividends))
                print("Total cost is: %f" % (totInvestmentCost))
                print("size tradingData: %i" % (len(tradingData)))
                print("Total gain is %f" % (gain))
            # Z[i][i] = gain
            Z[i][j] = gain
            # Z[j][i] = gain
            # worksheet.write(i + 1, i + 1, 0)
            worksheet.write(i + 1, j + 1, gain)
            # worksheet.write(j + 1, i + 1, 0)

except Exception as e:
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    print(exc_type, fname, exc_tb.tb_lineno)
# print("Size portfolio on mingain: %f" % (min_tot_portfolio))
print("Min_min_ma is %i" % (min_min_ma))
print("Min_min_ma is %i" % (min_max_ma))
print("Max_min_ma is %i" % (max_min_ma))
print("Max_max_ma is %i" % (max_max_ma))
# print("Size portfolio on maxgain: %f" % (max_tot_portfolio))
# Done writing to excel -> Close the file
print('****** Done writing to Worksheet ******')
workbook.close()
print('****** Closed Workbook ******')
# Try to create 3D surface
print("Creata 3D surface plot")
fig = plt.figure()
ax = fig.gca(projection='3d')
X = np.arange(start_MA, end_MA+5, 5)
Y = np.arange(start_MA, end_MA+5, 5)
X, Y = np.meshgrid(X, Y)
print(X.shape)
print(Y.shape)
print(Z.shape)
surf = ax.plot_surface(X, Y, Z, rstride=1, cstride=1, cmap=cm.coolwarm,
                       linewidth=0, antialiased=False)
ax.set_zlim(min_gain*0.9, max_gain*1.1)

ax.zaxis.set_major_locator(LinearLocator(10))
ax.zaxis.set_major_formatter(FormatStrFormatter('%.02f'))

fig.colorbar(surf, shrink=0.5, aspect=5)

plt.show()
