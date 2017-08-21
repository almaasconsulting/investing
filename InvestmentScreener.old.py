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
import ChowderComputer as cc
from FTP import FTPTransfer as ft
import urllib.request
import MarginOfSafetyCalculator as mos
import MACDStrategy as macd

debug = False
# define db-file
dbfile = "db/stocks.db"
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
    stockList = ['MDT']
else:
    stockList = []
    query1 = """select * from stockinfo si where (instr(si.ticker, '.OL') or
               instr(si.ticker, '.TO') or instr(si.ticker, '.V'))
                and si.ticker in
               (select ad.ticker from annual_dividends ad where
                ad.year > 2014 and ad.year < 2017)"""

    query = """select * from stockinfo si where (instr(si.ticker, '.OL') or
               instr(si.ticker, '.TO') or instr(si.ticker, '.V') or
               instr(si.ticker, '.L') or instr(si.ticker, '.IL') or
               not instr(si.ticker, '.')) and si.ticker in
               (select ad.ticker from annual_dividends ad where ad.year > 2014)
               and si.isActive > 0"""

    query2 =  """select * from stockinfo si where (instr(si.ticker, '.OL')) and si.ticker in
               (select ad.ticker from annual_dividends ad where ad.year > 2014)
               and si.isActive > 0"""
    query3 = """select * from stockinfo si where (instr(si.ticker, '.OL'))
               and si.isActive > 0"""
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
        query_str = ("Select * from annual_dividends ad where ad.ticker = '%s' order by ad.year desc"
                     % (stock[0]))
        cur.execute(query_str)
        stockData = cur.fetchone()
        if stockData:
            f = web.DataReader(stock[0], 'yahoo', start, end)
            # print(list(f.columns.values))
            if debug:
                print('****** Create Moving Average Data ******')
            closeList = pd.Series(f['Adj Close'])

            # ema60 = closeList.ewm(span=60, min_periods=0, ignore_na=False,
            #                       adjust=True).mean()
            emaFast = closeList.ewm(span=150, min_periods=0, ignore_na=False,
                                  adjust=True).mean()
            emaSlow = closeList.ewm(span=300, min_periods=0, ignore_na=False,
                                   adjust=True).mean()
            sameList = pd.concat([closeList, emaFast, emaSlow], axis=1)

            if debug:
                print(ema65)
                print(ema165)
                print(closeList)
                print("samelist is:")
                print(sameList)
                print("was samelist..")
            sameList.columns = ['Close', 'ema Fast', 'ema Slow']
            if debug:
                print('****** Done Creating Moving Average Data ******')

            # print(sameList.iloc[[2]])
            # Create an array of MA's to Test
            maTestList = ['Close', 'ema Fast', 'ema Slow']
            # Call function for computing 52 WL

            trades52WL = isf.compute52WL(sameList, 'Close', maTestList[1],
                                         maTestList[2])
            valueMACross = tsf.computeMACrossOver(sameList, 'Close', maTestList[1], maTestList[2])
            chowderScore5 = cc.computeChowderNumberForStock(conn, 2012, 2016, stock[0])
            # chowderScore5 = cc.computeChowderNumberForStock(conn, 2012, 2016, stock[0])
            chowderScore3 = cc.computeChowderNumberForStock(conn, 2014, 2016, stock[0])
            chowderScore2 = cc.computeChowderNumberForStock(conn, 2015, 2016, stock[0])
            """
            trades52WL = False
            valueMACross = False
            chowderScore5 = False
            chowderScore3 =  False
            chowderScore2 =  False
            """
            macdTrades = macd.computeMACDStrategy(f)
            # valueGuppy = tam.computeGuppyMACrossOver(sameList, 'Close',
            #              'ema 15', 'ema 30', 'ema 40')
            # Now write the data to excel
            # First ' 52 Week Low'
            if trades52WL:

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
                    worksheet.write(row, col + 1, item[1])
                    worksheet.write(row, col + 2, item[2])
                    worksheet.write(row, col + 3, "52 Week Low")
                    screenerResult.append([stock[0], "52 Week Low", "Shareprice", item[2],str(item[1]),dato])
            if valueMACross:
                item = valueMACross[len(valueMACross)-1]
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
                    if dato - int(item[1]) < 6:
                        is_ok = True

                if is_ok:
                    print("MACrossover - strategy added %s to screenlist - "
                          % (stock[0]))
                    row = row + 1
                    worksheet.write(row, col, stock[0])
                    worksheet.write(row, col + 1, item[1])
                    worksheet.write(row, col + 2, item[2])
                    worksheet.write(row, col + 3, "MACrossover")
                    screenerResult.append([stock[0], "MA Crossover", "Shareprice", item[2],str(item[1]), dato])
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
            if chowderScore5:
                mosValues = mos.computeMarginOfSafety(chowderScore5[5], float(stockData[2]), chowderScore5[4],chowderScore5[3])
                # Chowder ok
                print("ChowderScore 5 year - strategy added %s to screenlist"
                       % (stock[0]))
                row = row + 1
                worksheet.write(row, col, stock[0])
                worksheet.write(row, col + 1, chowderScore5[6])
                worksheet.write(row, col + 2, chowderScore5[5])
                worksheet.write(row, col + 3, "ChowderScore 5 year")
                worksheet.write(row, col + 4, chowderScore5[1])
                worksheet.write(row, col + 5, chowderScore5[2])
                worksheet.write(row, col + 6, chowderScore5[3])
                worksheet.write(row, col + 7, chowderScore5[4])
                worksheet.write(row, col + 8, float(stockData[2]))
                worksheet.write(row, col + 9, mosValues[0])
                worksheet.write(row, col + 10, mosValues[1])
                worksheet.write(row, col + 11, mosValues[2])
                screenerResult.append([stock[0], "ChowderScore 5 year", "Chowder Value", chowderScore5[2], str(dato), dato ] )
                screenerResult.append([stock[0], "ChowderScore 5 year", "Chowder Part", chowderScore5[3], str(dato), dato ] )
                screenerResult.append([stock[0], "ChowderScore 5 year", "Current div. yield", chowderScore5[4], str(dato), dato ] )
                screenerResult.append([stock[0], "Margin Of Safety 5 Year", "Fair Value", mosValues[0],  str(dato), dato ])
                screenerResult.append([stock[0], "Margin Of Safety 5 Year", "MOS Value", mosValues[1],  str(dato), dato ])
                screenerResult.append([stock[0], "Margin Of Safety 5 Year", "Growth Potential", mosValues[2],  str(dato), dato ])

            if chowderScore3:
                mosValues = mos.computeMarginOfSafety(chowderScore3[5], float(stockData[2]), chowderScore3[4],chowderScore3[3])
                # Chowder ok
                print("ChowderScore 3 year - strategy added %s to screenlist"
                       % (stock[0]))
                row = row + 1
                worksheet.write(row, col, stock[0])
                worksheet.write(row, col + 1, chowderScore3[6])
                worksheet.write(row, col + 2,chowderScore3[5])
                worksheet.write(row, col + 3, "ChowderScore 3 year")
                worksheet.write(row, col + 4, chowderScore3[1])
                worksheet.write(row, col + 5, chowderScore3[2])
                worksheet.write(row, col + 6, chowderScore3[3])
                worksheet.write(row, col + 7, chowderScore3[4])
                worksheet.write(row, col + 8, float(stockData[2]))
                worksheet.write(row, col + 9, mosValues[0])
                worksheet.write(row, col + 10, mosValues[1])
                worksheet.write(row, col + 11, mosValues[2])
                screenerResult.append([stock[0], "ChowderScore 3 year", "Chowder Value", chowderScore3[2], str(dato), dato ] )
                screenerResult.append([stock[0], "ChowderScore 3 year", "Chowder Part", chowderScore3[3], str(dato), dato ] )
                screenerResult.append([stock[0], "ChowderScore 3 year", "Current div. yield", chowderScore3[4], str(dato), dato ] )
                screenerResult.append([stock[0], "Margin Of Safety 3 Year", "Fair Value", mosValues[0],  str(dato), dato ])
                screenerResult.append([stock[0], "Margin Of Safety 3 Year", "MOS Value", mosValues[1],  str(dato), dato ])
                screenerResult.append([stock[0], "Margin Of Safety 3 Year", "Growth Potential", mosValues[2],  str(dato), dato ])

            if chowderScore2:
                # Chowder ok
                mosValues = mos.computeMarginOfSafety(chowderScore2[5], float(stockData[2]), chowderScore2[4],chowderScore2[3])
                print("ChowderScore 2 year - strategy added %s to screenlist"
                       % (stock[0]))
                row = row + 1
                worksheet.write(row, col, stock[0])
                worksheet.write(row, col + 1, chowderScore2[6])
                worksheet.write(row, col + 2,chowderScore2[5])
                worksheet.write(row, col + 3, "ChowderScore 2 year")
                worksheet.write(row, col + 4, chowderScore2[1])
                worksheet.write(row, col + 5, chowderScore2[2])
                worksheet.write(row, col + 6, chowderScore2[3])
                worksheet.write(row, col + 7, chowderScore2[4])
                worksheet.write(row, col + 8, float(stockData[2]))
                worksheet.write(row, col + 9, mosValues[0])
                worksheet.write(row, col + 10, mosValues[1])
                worksheet.write(row, col + 11, mosValues[2])
                screenerResult.append([stock[0], "ChowderScore 2 year", "Chowder Value", chowderScore2[2], str(dato), dato ] )
                screenerResult.append([stock[0], "ChowderScore 2 year", "Chowder Part", chowderScore2[3], str(dato), dato ] )
                screenerResult.append([stock[0], "ChowderScore 2 year", "Current div. yield", chowderScore2[4], str(dato), dato ] )
                screenerResult.append([stock[0], "Margin Of Safety 2 Year", "Fair Value", mosValues[0],  str(dato), dato ])
                screenerResult.append([stock[0], "Margin Of Safety 2 Year", "MOS Value", mosValues[1],  str(dato), dato ])
                screenerResult.append([stock[0], "Margin Of Safety 2 Year", "Growth Potential", mosValues[2],  str(dato), dato ])
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
# Now create the file for webpage
csv_df = pd.DataFrame(screenerResult)
csv_df.to_csv("screener_results.csv", index=False, header=False)
ftpConn = ft.createFTPConnection("ftp.dividendgrowth.no", "dividendgrowth.no", "Al10maas!")
ft.testConnection(ftpConn)
file2Upload = "screener_results.csv"
ft.ftpUploadBinary(ftpConn, file2Upload)
ft.closeConnection(ftpConn)
# Process file on server
with urllib.request.urlopen("http://dividendgrowth.no/modules/UpdateScreenerResults.php?file=" + file2Upload) as response:
    html = response.read()