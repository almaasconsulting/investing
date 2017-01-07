"""Module for StockInformation."""
import time
# User generated modules
import databaseOPS as dbops
import JSONOps as jops
import NetfondsStockReader as nsr
import NYSEStockReader as nysr

"""This module should try to insert and update stocks in the database

Changelog:
Date:           Init:       Comment:
*******************************************************************************
21.07.2016      AA          Version 1.
"""


def insertStockInformation(db, inDir, stockfile):
    """Method for performing the insertion ."""
    data = jops.getListFromJSON(inDir, stockfile)
    i = 1
    total = 0
    if data:
        # Perform inserts here.
        total = len(data)
        for item in data:
            exchange = item['Exchange']
            name = item["Name"]
            ticker = item["Ticker"]
            category = item["categoryName"]
            inserttime = time.time()
            print("stock nr %s of %s -> ticker is: %s" % (i, total, ticker))
            i = i + 1
            values = [ticker, name, exchange, category, inserttime]
            c = db.cursor()
            c.execute("""insert or replace into stockinfo
            (ticker, name, exchange, category, last_change) values
                     (?,?,?,?,?)""", values)
            db.commit()
    else:
        print("Error..")

def insertStockInformationFromURL(db, country, exchange):
    """Method for performing the insertion from reading urls."""
    if country == "USA":
        stockList = nysr.createStockListByExchange(exchange)
    elif country == "NORWAY":
        stockList = nsr.createStockList()

    i = 1
    total = 0
    if stockList:
        # Perform inserts here.
        total = len(stockList)
        for item in stockList:
            name = ""
            ticker = item
            category = ""
            inserttime = time.time()
            print("stock nr %s of %s -> ticker is: %s" % (i, total, ticker))
            i = i + 1
            values = [ticker, name, exchange, category, inserttime]
            c = db.cursor()
            c.execute("""insert or replace into stockinfo
            (ticker, name, exchange, category, last_change) values
                     (?,?,?,?,?)""", values)
            db.commit()
    else:
        print("Error..")

# Creat test method for testing the yahooFinanceDataReader.
def main():
    """Test method for testing the module."""
    db = dbops.connectToDatabase("db", "stocks.db")
    insertStockInformationFromURL(db, "USA", "nyse")
    insertStockInformationFromURL(db, "USA", "amex")
    insertStockInformationFromURL(db, "USA", "nasdaq")
    insertStockInformationFromURL(db, "NORWAY", "OSE")
    insertStockInformation(db, "infiles", "Stock.json")


if __name__ == "__main__":
    main()
