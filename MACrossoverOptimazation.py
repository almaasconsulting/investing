"""Optimal MA crossover strategy testing including dividends."""
import pandas_datareader.data as web
import pandas as pd
import datetime
import matplotlib.pyplot as plt
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
debug = False

stock = "ASC.OL"
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
# Add worksheet for result data
print('****** Create Worksheets to workbook ******')
# Create worksheet for trades
worksheet = workbook.add_worksheet('CrossoverData')
# Add headers to worksheet should add on horizontal and vertical
for i in range(1, 41):
    worksheet.write(i, 0, str(i*5))
    worksheet.write(0, i, str(i*5))

# Headers for the table is generated
# Now read the shareprice data
print("Testing stock %s " % (stock))
try:
    f = web.DataReader(stock, 'yahoo', start, end)
    print(list(f.columns.values))
    print('****** Create Moving Average Data ******')
    closeList = pd.Series(f['Adj Close'])
    emaList = []
    for i in range(1, 41):
        ema = pd.ewma(f['Adj Close'], span=i*5)
        ema.columns = "%i" % (i*5)
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

    # Sort the data such that the dividends are from start to end
    dividendData.sort(key=lambda x: x[0])
    # Now all the required data is aqquired for doing the tests.
    for i in range(0, 1):
        v = i+1
        for j in range(v, 2):
            print(type(emaList[j]))
            tradingData = macf.computeMACrossOver(closeList, emaList[i], emaList[j])
            print("size tradingData: %i" % (len(tradingData)))

    list1 = emaList[0]
    print(len(list1))

except Exception as e:
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    print(exc_type, fname, exc_tb.tb_lineno)
# Done writing to excel -> Close the file
print('****** Done writing to Worksheet ******')
workbook.close()
print('****** Closed Workbook ******')
