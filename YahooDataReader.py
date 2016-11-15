"""Module for reading data from yahoo finance."""
import io
import csv
import urllib.request

"""YahooDataReader.py"""

"""
Changelog:
Date:           Init:       Comment:
*******************************************************************************
13.07.2016      AA          Version 1.
30.07.2016      AA          Finished also for fundamental info, uses
                            dataParameters for storing symbols for fundamental
                            information.
"""
debug = False


def yahooFinanceDataReader(ticker, period, dataParameters, type):
    """Method for reading from yahoo finance, depending on type."""
    url = ""
    if type == 'dividend':

        starturl = "http://real-chart.finance.yahoo.com/table.csv?s="
        midurl = "&c="
        endurl = "&g=v"
        url = url.join((starturl, ticker[0], midurl, str(period[0]), endurl))
        if debug:
            print(url)
        # Now we have created the correct url, then fetch the file from
        # the internet
    elif type == 'fundamental':
        """
        s = ticker, n = name, y = dividend_yie
        """
        tickers = ""
        if len(ticker) > 1:
            tickers = "+"
            tickers = tickers.join(ticker)
        else:
            tickers = ticker[0]
        # print("tickers er : %s" % (tickers))
        starturl = "http://finance.yahoo.com/d/quotes.csv?s="
        parameterurl = ''.join(dataParameters)
        parameterurl = "&f=" + parameterurl
        url = starturl + tickers + parameterurl
        if debug:
            print(url)
    elif type == 'dailyprice':
        """Type is share price data"""
        starturl = "http://ichart.finance.yahoo.com/table.csv?s="
        tourl = "&d=" + str(period[4]) + "&e=" + str(period[3])
        tourl = tourl + "&f=" + str(period[5])
        fromurl = "&a=" + str(period[1]) + "&b=" + str(period[0])
        fromurl = fromurl + "&c=" + str(period[2])
        midurl = "&g=d"
        endurl = "&ignore=.csv"
        url = url.join((starturl, ticker, tourl, fromurl, midurl, endurl))
        if debug:
            print(url)
    # test if url > 0 and try to read, return false if error, else return array
    # the reading is common for all methods.
    try:
        csvfile = urllib.request.urlopen(url)
        datareader = csv.reader(io.TextIOWrapper(csvfile))
        dataAll = list(datareader)
        if type != "fundamental":
            dataWithoutHeaders = dataAll[1:]
            if len(dataWithoutHeaders) > 2:
                if debug:
                    for row in dataWithoutHeaders:
                        print(row)
                return dataWithoutHeaders
            else:
                return False
        else:
            if len(dataAll) > 0:
                if debug:
                    for row in dataAll:
                        print(row)
                return dataAll
            else:
                return False
    except:
        return False


# Creat test method for testing the yahooFinanceDataReader.
def main():
    """Test method for testing the module."""
    yahooFinanceDataReader(["T"],
                           [1, 1, 2000, 31, 12, 2020], [], "dividend")

if __name__ == "__main__":
    main()
