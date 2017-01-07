"""NASDAQ.com READ companies from CSV dump."""

import csv
import urllib.request

url_NASDAQ = 'http://www.nasdaq.com/screening/companies-by-name.aspx?letter=0&exchange=nasdaq&render=download'
url_NYSE = 'http://www.nasdaq.com/screening/companies-by-name.aspx?letter=0&exchange=nyse&render=download'
url_AMEX = 'http://www.nasdaq.com/screening/companies-by-name.aspx?letter=0&exchange=amex&render=download'

def readStockListData(url):
    stockList = []
    response = urllib.request.urlopen(url)
    cr = csv.reader(response.read().decode('iso-8859-1').splitlines())
    isFirst = True
    for row in cr:
        if isFirst:
            isFirst = False
        else:
            # print(row[0])
            stockList.append(row[0].strip())
    # print(stockList)
    return stockList


def createStockList():
    stockList = []
    stockList.extend(readStockListData(url_NASDAQ))
    stockList.extend(readStockListData(url_NYSE))
    stockList.extend(readStockListData(url_AMEX))
    return stockList

def createStockListByExchange(exchange):
    """Create a list of stocks from a given exchange."""
    stockList = []
    if exchange == "nasdaq":
        stockList.extend(readStockListData(url_NASDAQ))
    elif exchange == "nyse":
        stockList.extend(readStockListData(url_NYSE))
    else:
        stockList.extend(readStockListData(url_AMEX))
    return stockList

# Creat test method for testing the yahooFinanceDataReader.
def main():
    """Test method for testing the module."""
    createStockList()

if __name__ == "__main__":
    main()
