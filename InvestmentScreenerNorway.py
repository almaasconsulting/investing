"""InvestmentScreener.py - Find investments based on 52WL strategy."""
import pandas_datareader.data as web
import pandas as pd
import datetime
# import matplotlib.pyplot as plt
import xlsxwriter
from time import gmtime, strftime,localtime, sleep
import os
import sys
import sqlite3
from datetime import date
import InvestmentScreenerFunctions as isf
import TradeSimulatorFunctions as tsf
import ChowderComputer as cc
from FTP import FTPTransfer as ft
import urllib.request
import MarginOfSafetyCalculator as mos
import MACDStrategy as macd

debug = False
# define db-file
dbfile = "db/stocks.db"
start = datetime.datetime(2000, 1, 1)
print(strftime("%Y-%m-%d_%H-%M-%S", localtime()))
end = datetime.datetime(2050, 1, 27)
print('****** Create Workbook ******')
excelOutfile = 'InvestmentScreenResult_%s.xlsx'%( strftime("%Y-%m-%d_%H-%M-%S", localtime()))
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
worksheet.write(row, col + 4, "Chowder Type")
worksheet.write(row, col + 5, "Chowder")
worksheet.write(row, col + 6, "Chowder Part")
worksheet.write(row, col + 7, "Div. Yield")
worksheet.write(row, col + 8, "Dividend")
worksheet.write(row, col + 9, "Fair Value")
worksheet.write(row, col + 10, "MOS Value")
worksheet.write(row, col + 11, "Growth Potential")
nr = 0
conn = sqlite3.connect(dbfile)
cur = conn.cursor()
screenerResult = []
if debug:
    # stockList = ['MDT','T']
    query2 =  """select * from stockinfo si where (instr(si.ticker, '.OL')) and si.ticker in
               (select ad.ticker from annual_dividends ad where ad.year > 2014)
               and si.isActive > 0"""
    cur.execute(query2)
    stockList = cur.fetchall()
else:
    stockList = []
    query1 = """select * from stockinfo si where (instr(si.ticker, '.OL') or
               instr(si.ticker, '.TO') or instr(si.ticker, '.V'))
                and si.ticker in
               (select ad.ticker from annual_dividends ad where
                ad.year > 2014 and ad.year < 2017)"""

    query = """select * from stockinfo si where (instr(si.ticker, '.OL') or
               instr(si.ticker, '.TO') or instr(si.ticker, '.V') or
               not instr(si.ticker, '.')) and si.ticker in
               (select ad.ticker from annual_dividends ad where ad.year > 2014)
               and si.isActive > 0"""

    query2 =  """select * from stockinfo si where (instr(si.ticker, '.OL')) and si.ticker in
               (select ad.ticker from annual_dividends ad where ad.year > 2014)
               and si.isActive > 0"""
    query3 = """select * from stockinfo si where (instr(si.ticker, '.OL'))
               and si.isActive > 0"""
    query4 = """select * from stockinfo si where (instr(si.ticker, '.OL'))  and si.isActive > 0"""
    cur.execute(query4)
    stockList = cur.fetchall()
    # print(len(items))
    print(len(stockList))

# stockList = ['AMSC.OL',]
for stock in stockList:
    print("Stock is: %s" %(stock[0]))
    nr = nr + 1
    # Test if stock in annualdividends, otherwise just skip.
    if nr > 1:
        print("Test stock %s" % (stock[0]))
        if nr % 2 < 1:
            print("Done with %i of %i" % (nr, len(stockList)))
            #sleep(stock = stock.replace('OL','OSE')
    ticker = stock[0].replace('OL','OSE')

    # print(ticker)
    try:
        # print("HERE")
        ticker = stock[0].replace('OL','OSE')
        # ticker = "STL.OSE"
        url = "http://hopey.netfonds.no/paperhistory.php?paper=" + ticker + "&csv_format=csv"
        # print(url)
        f = pd.read_csv(url, names=['quote_date','paper','exch','open','high','low','close','volume','value'],header=None)
        # print(pd.Series(f['close']))
        # print("HERE")
        # print(list(f.columns.values))
        if debug:
            print('****** Create Moving Average Data ******')
        closeList = pd.Series(f['close']).ix[1:].iloc[::-1]
        openList = pd.Series(f['open']).ix[1:].iloc[::-1]
        dateList = pd.Series(f['quote_date']).ix[1:].iloc[::-1]
        # closeList = pd.Series(f['close']).ix[1:]
        # print(closeList)

        # ema60 = closeList.ewm(span=60, min_periods=0, ignore_na=False,
        #                       adjust=True).mean()
        emaFast = closeList.ewm(span=150, min_periods=0, ignore_na=False,
                              adjust=True).mean()
        # print(emaFast)
        emaSlow = closeList.ewm(span=300, min_periods=0, ignore_na=False,
                               adjust=True).mean()
        sameList = pd.concat([closeList, emaFast, emaSlow,pd.Series(f['quote_date']).ix[1:].iloc[::-1]], axis=1)

        # print(emaFast)
        # print(emaSlow)
        if debug:
            print(ema65)
            print(ema165)
            print(closeList)
            print("samelist is:")
            print(sameList)
            print("was samelist..")
        sameList.columns = ['close', 'ema Fast', 'ema Slow','dato']

        if debug:
            print('****** Done Creating Moving Average Data ******')

        # print(sameList.iloc[[2]])
        # Create an array of MA's to Test
        maTestList = ['close', 'ema Fast', 'ema Slow']
        # Call function for computing 52 WL

        trades52WL = isf.compute52WL(sameList, 'close', maTestList[1],
                                     maTestList[2],'dato')
        # chowderScore5 = cc.computeChowderNumberForStock(conn, 2012, 2016, stock[0])
        # chowderScore5 = cc.computeChowderNumberForStock(conn, 2012, 2016, stock[0])
        #chowderScore3 = cc.computeChowderNumberForStock(conn, 2014, 2016, stock[0])
        macdTrades = macd.computeMACDStrategy(closeList,emaFast,emaSlow, openList, dateList, 75, 100, 50, ticker)
        # valueGuppy = tam.computeGuppyMACrossOver(sameList, 'Close',
        #              'ema 15', 'ema 30', 'ema 40')
        # Now write the data to excel
        # First ' 52 Week Low'
        if trades52WL:
            print("in trades52WL TEST")
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
                print("item[1] is %i and datoen is %i" % (int(item[1]),
                      dato))

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
                worksheet.write(row, col + 1, item[1])
                worksheet.write(row, col + 2, item[2])
                worksheet.write(row, col + 3, "52 Week Low")
                screenerResult.append([stock[0], "52 Week Low", "Shareprice", item[2],str(item[1]),dato])
        if macdTrades:
            item = macdTrades[len(macdTrades)-1]
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
                print("item[1] is %i and datoen is %i" % (int(item[1]),
                      dato))
                debug = False
            is_ok = False
            if yearTrade < year_today:
                if dato - int(item[1]) < 8875:
                    is_ok = True
            elif monthTrade < month_today:
                if dato - int(item[1]) < 75:
                    is_ok = True
            else:
                if dato - int(item[1]) < 20:
                    is_ok = True

            if is_ok:
                print("MACD - strategy added %s to screenlist"
                      % (stock[0]))
                row = row + 1
                worksheet.write(row, col, stock[0])
                worksheet.write(row, col + 1, item[1])
                worksheet.write(row, col + 2, item[2])
                worksheet.write(row, col + 3, "MACD Strategy")
                screenerResult.append([stock[0], "MACD Strategy", "Shareprice", item[2],str(item[1]),dato])

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        # print(exc_type, fname, exc_tb.tb_lineno)
conn.close()
print("Done with %i stocks" % (len(stockList)))
# Done writing to excel -> Close the file
print('****** Done writing to Worksheet ******')
workbook.close()
print('****** Closed Workbook ******')
