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
stockList = ["T"]
for stock in stockList:
    nr = nr + 1
    print("Testing stock %s -> nr %i of %i" % (stock, nr, len(stockList)))
    try:
        f = web.DataReader(stock, 'yahoo', start, end)
        print(list(f.columns.values))
        print('****** Create Moving Average Data ******')
        closeList = pd.Series(f['Adj Close'])
        ema65 = pd.ewma(f['Adj Close'], span=65)
        ema70 = pd.ewma(f['Adj Close'], span=70)
        ema75 = pd.ewma(f['Adj Close'], span=75)
        ema145 = pd.ewma(f['Adj Close'], span=145)
        ema155 = pd.ewma(f['Adj Close'], span=155)
        ema165 = pd.ewma(f['Adj Close'], span=165)
        # Call function for computing 52 low
        sameList = pd.concat([closeList, ema65, ema70, ema75, ema145, ema155,
                              ema165], axis=1)

        sameList.columns = ['Close', 'ema 65', 'ema 70', 'ema 75', 'ema 145',
                            'ema 155', 'ema 165']
        print('****** Done Creating Moving Average Data ******')

        # print(sameList.iloc[[2]])
        # Create an array of MA's to Test
        maTestList = ['ema 65', 'ema 70', 'ema 75', 'ema 145', 'ema 155',
                      'ema 165']

        pos = 0
        j = 0
        k = 0
        # for pos in range(1,len(maTestList)-1):
            # for j in range(pos+1, len(maTestList)):
        for pos in range(0, 5):
            for j in range(pos+1, 6):
                value52WL = tam.compute52WLPoints(sameList, 'Close', maTestList[pos], maTestList[j])
                valueMACross = tam.computeMACrossOver(sameList, 'Close', maTestList[pos], maTestList[j])
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
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)

# Done writing to excel -> Close the file
print('****** Done writing to Worksheet ******')
workbook.close()
print('****** Closed Workbook ******')
