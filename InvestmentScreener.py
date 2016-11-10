"""InvestmentScreener.py - Find investments based on 52WL strategy"""
import pandas_datareader.data as web
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import xlsxwriter
import time
import os
import sys
from datetime import date
import TradeSimulatorFunctions as tsf
import NetfondsStockReader as nsr

debug = False

start = datetime.datetime(2000, 1, 1)
end = datetime.datetime(2050, 1, 27)
print('****** Create Workbook ******')
excelOutfile = 'InvestmentScreenResult.xlsx'
# Test if excelOutfile exists, remove and create new one
if os.path.isfile(excelOutfile):
    os.remove(excelOutfile)
workbook = xlsxwriter.Workbook(excelOutfile)
row = 0
col = 0
# Add worksheet for result data
print('****** Create Worksheet to workbook ******')
worksheet = workbook.add_worksheet('Result')
# Add headers to worksheet
worksheet.write(row, col, "Stock")
worksheet.write(row, col + 1, "Signal Date")
worksheet.write(row, col + 2, "Share price")
stockList = nsr.createStockList()
nr = 0
if debug:
    stockList = ['STL.OL']
for stock in stockList:
    nr = nr + 1
    print("Testing stock %s -> nr %i of %i" % (stock, nr, len(stockList)))
    try:
        f = web.DataReader(stock, 'yahoo', start, end)
        # print(list(f.columns.values))
        if debug:
            print('****** Create Moving Average Data ******')
        closeList = pd.Series(f['Adj Close'])
        ema15 = pd.ewma(f['Adj Close'], span=15)
        ema30 = pd.ewma(f['Adj Close'], span=30)
        ema40 = pd.ewma(f['Adj Close'], span=40)
        ema50 = pd.ewma(f['Adj Close'], span=50)
        ema100 = pd.ewma(f['Adj Close'], span=100)
        ema200 = pd.ewma(f['Adj Close'], span=200)
        # Call function for computing 52 WL
        sameList = pd.concat([closeList, ema15, ema30, ema40, ema50, ema100, ema200], axis=1)

        # print(sameList[1])
        # ema15List = list(ema15.columns.values)
        # print(ema15List)
        sameList.columns = ['Close', 'ema 15', 'ema 30', 'ema 40','ema 50', 'ema 100', 'ema 200']
        if debug:
            print('****** Done Creating Moving Average Data ******')

        # print(sameList.iloc[[2]])
        # Create an array of MA's to Test
        maTestList = ['ema 15', 'ema 30', 'ema 40', 'ema 50', 'ema 100', 'ema 200']
        trades52WL = tsf.compute52WLTrades(sameList, 'Close', maTestList[1], maTestList[3])
        # valueMACross = tam.computeMACrossOver(sameList, 'Close', maTestList[pos], maTestList[j])
        # valueGuppy = tam.computeGuppyMACrossOver(sameList, 'Close', 'ema 15', 'ema 30', 'ema 40')
        # Now write the data to excel
        # First ' 52 Week Low'
        if len(trades52WL) > 1:
            item = trades52WL[len(trades52WL)-1]
            today = date.today()
            dato = int(str(today).replace("-", ""))
            if debug:
                print(today)
                print(type(dato))
                print(dato)
                print(type(item[1]))

            if int(item[1]) > dato - 31:
                print("Added %s to screenlist" % (stock))
                row = row + 1
                worksheet.write(row, col, stock)
                worksheet.write(row, col + 1, item[0])
                worksheet.write(row, col + 2, item[2])

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)

# Done writing to excel -> Close the file
print('****** Done writing to Worksheet ******')
workbook.close()
print('****** Closed Workbook ******')
