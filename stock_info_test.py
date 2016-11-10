import pandas_datareader.data as web
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import xlsxwriter
import time
import os
import sys
import TAMethods as tam
import NetfondsStockReader as nsr


start = datetime.datetime(2000, 1, 1)
end = datetime.datetime(2022, 1, 27)
print('****** Create Workbook ******')
excelOutfile = 'TradingTestData.xlsx'
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
worksheet.write(row, col + 1, "Indicator")
worksheet.write(row, col + 2, "MA 1")
worksheet.write(row, col + 3, "MA 2")
worksheet.write(row, col + 4, "# of trades")
worksheet.write(row, col + 5, "Portfolio size")
worksheet.write(row, col + 6, "\% gain")
worksheet.write(row, col + 7, "Tot invested")
worksheet.write(row, col + 8, "Tot value")
stockList = nsr.createStockList()

nr = 0
stockList = ["STL.OL"]
for stock in stockList:
    nr = nr + 1
    print("Testing stock %s -> nr %i of %i" % (stock, nr, len(stockList)))
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
        # ema200 = closeList.ewm(f['Close'], span=200, min_periods=0, ignore_na=False, adjust=True ).mean()
        ema200 = pd.ewma(f['Adj Close'], span=200)
        # Call function for computing 52 WL
        # print(closeList)
        # print(closeList[0])
        sameList = pd.concat([closeList, ema15, ema30, ema40, ema50, ema100, ema200], axis=1)

        # print(sameList[1])
        # ema15List = list(ema15.columns.values)
        # print(ema15List)
        sameList.columns = ['Close', 'ema 15', 'ema 30', 'ema 40','ema 50', 'ema 100', 'ema 200']
        print('****** Done Creating Moving Average Data ******')

        # print(sameList.iloc[[2]])
        # Create an array of MA's to Test
        maTestList = ['ema 15', 'ema 30', 'ema 40', 'ema 50', 'ema 100', 'ema 200']

        pos = 0
        j = 0
        k = 0
        # for pos in range(1,len(maTestList)-1):
            # for j in range(pos+1, len(maTestList)):
        for pos in range(0, 2):
            for j in range(pos+1, 3):
                value52WL = tam.compute52WLPoints(sameList, 'Close', maTestList[pos], maTestList[j])
                # valueMACross = tam.computeMACrossOver(sameList, 'Close', maTestList[pos], maTestList[j])
                # valueGuppy = tam.computeGuppyMACrossOver(sameList, 'Close', 'ema 15', 'ema 30', 'ema 40')
                # Now write the data to excel
                # First ' 52 Week Low'
                row = row + 1
                worksheet.write(row, col, stock)
                worksheet.write(row, col + 1, '52 Week Low')
                worksheet.write(row, col + 2, maTestList[pos])
                worksheet.write(row, col + 3, maTestList[j])
                worksheet.write(row, col + 4, value52WL[0])
                worksheet.write(row, col + 5, value52WL[1])
                worksheet.write(row, col + 6, value52WL[2])
                worksheet.write(row, col + 7, value52WL[3])
                worksheet.write(row, col + 8, value52WL[4])
                # Second ' MA Cross'
                row = row + 1
                worksheet.write(row, col, stock)
                worksheet.write(row, col + 1, 'MA Cross')
                worksheet.write(row, col + 2, maTestList[pos])
                worksheet.write(row, col + 3, maTestList[j])
                worksheet.write(row, col + 4, valueMACross[0])
                worksheet.write(row, col + 5, valueMACross[1])
                worksheet.write(row, col + 6, valueMACross[2])
                worksheet.write(row, col + 7, valueMACross[3])
                worksheet.write(row, col + 8, valueMACross[4])
    except:
        print("Unexpected error:", sys.exc_info()[0])

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
