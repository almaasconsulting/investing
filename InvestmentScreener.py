"""InvestmentScreener.py - Find investments based on 52WL strategy."""
import pandas_datareader.data as web
import pandas as pd
import datetime
# import matplotlib.pyplot as plt
import xlsxwriter
import time
import os
import sys
import sqlite3
from datetime import date
import InvestmentScreenerFunctions as isf
import TradeSimulatorFunctions as tsf


debug = False
# define db-file
dbfile = "db/test.db"
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
worksheet.write(row, col + 3, "Signal Type")
nr = 0
conn = sqlite3.connect(dbfile)
cur = conn.cursor()
if debug:
    stockList = ['ASC.OL']
else:
    stockList = []
    query = """select * from stockinfo si where (instr(si.ticker, '.OL') or
               instr(si.ticker, '.TO') or instr(si.ticker, '.V') or
               instr(si.ticker, '.L') or instr(si.ticker, '.IL') or
               not instr(si.ticker, '.')) and si.ticker in
               (select ad.ticker from annual_dividends ad where
                ad.year > 2014 and ad.year < 2017)"""

    query2 = """select si.ticker from stockinfo si where si.ticker in
                (select ad.ticker from annual_dividends ad where
                ad.year > 2014 and ad.year < 2017)"""
    cur.execute(query)
    stockList = cur.fetchall()
    # print(len(items))
    print(len(stockList))

# Create connection to db
# stockList = ['ASC.OL']
print("Start processing the list of stocks")
for stock in stockList:
    nr = nr + 1
    # Test if stock in annualdividends, otherwise just skip.
    if debug:
        print("Test stock %s" % (stock[0]))
    if nr > 49:
        if nr % 50 < 1:
            print("Done with %i of %i" % (nr, len(stockList)))
            time.sleep(2)
    try:
        query_str = ("Select * from annual_dividends ad where ad.ticker = '%s'"
                     % (stock[0]))
        cur.execute(query_str)
        if cur.fetchone():
            # print("IS HERE")
            f = web.DataReader(stock[0], 'yahoo', start, end)
            # print(list(f.columns.values))
            if debug:
                print('****** Create Moving Average Data ******')
            closeList = pd.Series(f['Adj Close'])

            # ema60 = closeList.ewm(span=60, min_periods=0, ignore_na=False,
            #                       adjust=True).mean()
            ema65 = closeList.ewm(span=65, min_periods=0, ignore_na=False,
                                  adjust=True).mean()
            ema165 = closeList.ewm(span=165, min_periods=0, ignore_na=False,
                                   adjust=True).mean()
            sameList = pd.concat([closeList, ema65, ema165], axis=1)

            if debug:
                print(sameList[1])
            sameList.columns = ['Close', 'ema 65', 'ema 165']
            if debug:
                print('****** Done Creating Moving Average Data ******')

            # print(sameList.iloc[[2]])
            # Create an array of MA's to Test
            maTestList = ['Close', 'ema 65', 'ema 165']
            # Call function for computing 52 WL
            trades52WL = isf.compute52WL(sameList, 'Close', maTestList[1],
                                         maTestList[2])
            valueMACross = tsf.computeMACrossOver(sameList, 'Close',
                                                  maTestList[2], maTestList[4])
            # valueGuppy = tam.computeGuppyMACrossOver(sameList, 'Close',
            #              'ema 15', 'ema 30', 'ema 40')
            # Now write the data to excel
            # First ' 52 Week Low'
            if len(trades52WL) > 0:
                item = trades52WL[len(trades52WL)-1]
                tradeDayList = item[0].split("-")
                yearTrade = int(tradeDayList[0])
                monthTrade = int(tradeDayList[1])
                dayTrade = int(tradeDayList[2])
                today = date.today()
                todayList = str(today).split("-")
                year_today = int(todayList[0])
                month_today = int(todayList[1])
                day_today = int(todayList[2])
                dato = int(str(today).replace("-", ""))
                if debug:
                    print(yearTrade)
                    print(monthTrade)
                    print(dayTrade)
                    print(year_today)
                    print(month_today)
                    print(day_today)
                    print("item[1] is %i and dato is %i" % (item[1], dato))
                    debug = False
                is_ok = False
                if yearTrade < year_today:
                    if dato - int(item[1]) < 8875:
                        is_ok = True
                elif monthTrade < month_today:
                    if dato - int(item[1]) < 75:
                        is_ok = True
                else:
                    if dato - int(item[1]) < 6:
                        is_ok = True

                if is_ok:
                    print("52 WeekLow - strategy added %s to screenlist"
                          % (stock[0]))
                    row = row + 1
                    worksheet.write(row, col, stock[0])
                    worksheet.write(row, col + 1, item[0])
                    worksheet.write(row, col + 2, item[2])
                    worksheet.write(row, col + 3, "52 Week Low")

            if len(valueMACross) > 1:
                item = valueMACross[len(valueMACross)-1]
                today = date.today()
                dato = int(str(today).replace("-", ""))
                if debug:
                    print(today)
                    print(type(dato))
                    print(dato)
                    print(type(item[1]))

                if int(item[1]) > dato - 5:
                    print("MACrossover - strategy added %s to screenlist - "
                          % (stock))
                    row = row + 1
                    worksheet.write(row, col, stock)
                    worksheet.write(row, col + 1, item[0])
                    worksheet.write(row, col + 2, item[2])
                    worksheet.write(row, col + 3, "MACrossover")
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        # print(exc_type, exc_obj, exc_tb.tb_lineno)
conn.close()
print("Done with %i stocks" % (len(stockList)))
# Done writing to excel -> Close the file
print('****** Done writing to Worksheet ******')
workbook.close()
print('****** Closed Workbook ******')
