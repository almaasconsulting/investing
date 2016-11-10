import pandas_datareader.data as web
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import xlsxwriter
import time
import os
import sys
# User created modules
import TradeSimulatorFunctions as tsf
import YahooDataReader as ydr
"""Simulating trading strategies including Dividends ."""
"""It should do the following:
    1) Run the strategy and for each trade do a insert in an array
    2) Try to see if there is any dividend-data for the stock.
       Iterate through this and for each dividend-data make a row in a
       dividend-array for date, divpr share and total shares at that moment
    3) As a clean-up summarize a total in # of stocks, total value and total
       dividend value paid.

"""


stock = "ASC.OL"

start = datetime.datetime(2006, 1, 1)
end = datetime.datetime(2022, 1, 27)
print('****** Create Workbook ******')
excelOutfile = 'TradingSimulationData.xlsx'
# Test if excelOutfile exists, remove and create new one
if os.path.isfile(excelOutfile):
    os.remove(excelOutfile)
workbook = xlsxwriter.Workbook(excelOutfile)
row = 0
col = 0
# Add worksheet for result data
print('****** Create Worksheets to workbook ******')
# Create worksheet for trades
worksheetTrades = workbook.add_worksheet('Trades')
# Add headers to worksheet
worksheetTrades.write(row, col, "Share")
worksheetTrades.write(row, col + 1, "Date")
worksheetTrades.write(row, col + 2, "Date Compressed")
worksheetTrades.write(row, col + 3, "Shareprice")
worksheetTrades.write(row, col + 4, "# of shares")
worksheetTrades.write(row, col + 5, "Acc. # of shares")
# Create worksheet for dividends
worksheetDividends = workbook.add_worksheet('Dividends')
# Add headers to worksheet
worksheetDividends.write(row, col, "Share")
worksheetDividends.write(row, col + 1, "Date")
worksheetDividends.write(row, col + 2, "Date Compressed")
worksheetDividends.write(row, col + 3, "Dividends")
worksheetDividends.write(row, col + 4, "Total Dividends")
print("Testing stock %s " % (stock))
try:
    f = web.DataReader(stock, 'yahoo', start, end)
    print(list(f.columns.values))
    print('****** Create Moving Average Data ******')
    closeList = pd.Series(f['Adj Close'])
    ema15 = pd.ewma(f['Adj Close'], span=15)
    ema30 = pd.ewma(f['Adj Close'], span=30)
    ema40 = pd.ewma(f['Adj Close'], span=40)
    ema50 = pd.ewma(f['Adj Close'], span=50)
    ema100 = pd.ewma(f['Adj Close'], span=100)
    ema200 = pd.ewma(f['Adj Close'], span=200)
    # Call function for computing 52 low
    sameList = pd.concat([closeList, ema15, ema30, ema40, ema50, ema100, ema200], axis=1)

    sameList.columns = ['Close', 'ema 15', 'ema 30', 'ema 40', 'ema 50', 'ema 100', 'ema 200']
    print('****** Done Creating Moving Average Data ******')

    # print(sameList.iloc[[2]])
    # Create an array of MA's to Test
    maTestList = ['ema 15', 'ema 30', 'ema 40', 'ema 50', 'ema 100', 'ema 200']
    trades52WL = tsf.compute52WLTrades(sameList, 'Close', maTestList[1], maTestList[3])
    # print(trades52WL)
    for item in trades52WL:
        # Now write the data to excel
        row = row + 1
        worksheetTrades.write(row, col, stock)
        worksheetTrades.write(row, col + 1, item[0])
        worksheetTrades.write(row, col + 2, item[1])
        worksheetTrades.write(row, col + 3, item[2])
        worksheetTrades.write(row, col + 4, item[3])
        worksheetTrades.write(row, col + 5, item[4])
    # Now fetch all dividend data for the given stock
    dividendData = ydr.yahooFinanceDataReader([stock],
                                              [1, 1, 2000, 31, 12, 2020], [],
                                              "dividend")
    # Sort the data such that the dividends are from start to end
    dividendData.sort(key=lambda x: x[0])
    # Now start to iterate through the items in the list
    row = 1

    pos = 0
    totDividends = 0
    for i in range(0, len(trades52WL)):
        fromElement = trades52WL[i]
        fromDate = int(fromElement[1])
        if i < len(trades52WL) - 1:
            toElement = trades52WL[i+1]
            toDate = int(toElement[1])
        else:
            toDate = 22001231

        for item in dividendData:
            divDate = int(item[0].replace("-", ""))
            if divDate-14 > fromDate and divDate-14 < toDate:
                # Do have a dividend for the amount in fromElement
                divAmount = float(fromElement[4]) * float(item[1])
                totDividends = totDividends + divAmount
                # Write the result in workbook
                worksheetDividends.write(row, col, stock)
                worksheetDividends.write(row, col + 1, item[0])
                worksheetDividends.write(row, col + 2, divDate)
                worksheetDividends.write(row, col + 3, divAmount)
                worksheetDividends.write(row, col + 4, totDividends)
                row = row + 1

except Exception as e:
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    print(exc_type, fname, exc_tb.tb_lineno)


# Done writing to excel -> Close the file
print('****** Done writing to Worksheet ******')
workbook.close()
print('****** Closed Workbook ******')
# print(sameList)
plt.plot(sameList['Close'], label='Close')
plt.plot(sameList['ema 15'], label='ema15')
plt.plot(sameList['ema 30'], label='ema30')
plt.plot(sameList['ema 50'], label='ema50')
plt.plot(sameList['ema 100'], label='ema100')
plt.plot(sameList['ema 200'], label='ema200')
legend = plt.legend(loc='upper center', shadow=True, fontsize='x-large')
# plt.show()

# print(f)
