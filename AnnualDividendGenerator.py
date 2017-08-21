"""Module for AnnualDividendGenerator."""
import time
from decimal import Decimal
# User generated modules
import YahooDataReader as ydr
import databaseOPS as dbops


"""This module should generate annual dividend data for a given stock.
    It should read data from yahoo finance and order the data such that it
    summarizes the dividend for each year. If it is for the last year(not the
    current year) is missing one dividend, then include the first one for the
    current year. Add everything to the table 'annual_dividends'

Changelog:
Date:           Init:       Comment:
*******************************************************************************
14.07.2016      AA          Version 1.
01.12.2017      AA          Updated to read from database instead
"""

debug = False


def computeAnnualDividend(db, ticker):
    """Compute the annual dividends for a given ticker."""
    # Function for computing the annual dividend for a given period for a
    # ticker. The ticker and id of ticker is given.
    # print("Ticker is %s" %(ticker))
    allDividends = ydr.yahooFinanceDataReader(ticker, [1985], [], "dividend")
    if allDividends:
        # Now start the computing, start reverse and find the first year after
        # that. This for ensure one has the whole year and not partial..
        # testList(allDividends)
        allDividends.reverse()
        # testList(allDividends)
        firstYearFound = False
        currYear = 0
        sum_years = 0
        dividend_sum = 0
        c = db.cursor()
        # delete all posts in annual_dividends for this ticker
        c.execute("""delete from annual_dividends where ticker = ?""",
                  [ticker])
        db.commit()
        for rowDiv in allDividends:
            if not firstYearFound:
                firstYear = int(rowDiv[0][0:4])
                currYear = int(rowDiv[0][0:4])
                firstYearFound = True
                dividend_sum = float(Decimal(rowDiv[1]))
                # print("NOW HERE %f" % (dividend_sum))
            else:
                tmpYear = int(rowDiv[0][0:4])
                if tmpYear > firstYear:
                    # Can continue to check if continuing on existing year
                    # or should test if in existing year
                    if tmpYear == currYear:
                        dividend_sum = dividend_sum + float(Decimal(rowDiv[1]))
                    elif tmpYear > currYear:
                        # write to database the result, first check if exists,
                        inserttime = time.time()
                        # Nr of periods of year
                        sum_years = sum_years + 1
                        values = [ticker, currYear, float(dividend_sum),
                                  sum_years, inserttime]
                        if currYear > firstYear:
                            insertAnnualDividend(db, values)
                            values = []
                        currYear = tmpYear
                        dividend_sum = float(Decimal(rowDiv[1]))
                        inserttime = time.time()
        if float(dividend_sum) > 0:
            inserttime = time.time()
            sum_years = sum_years + 1
            values = [ticker, currYear, float(dividend_sum), sum_years,
                      inserttime]
            insertAnnualDividend(db, values)

        values = []



def insertAnnualDividend(db, values):
    """Method for performing the insert in database."""
    try:
        if debug:
            print(values)
        c = db.cursor()
        c.execute("""insert or replace into annual_dividends
        (ticker, year, dividends, nr_of_periods, last_change) values
        (?,?,?,?,?)""", values)
        db.commit()
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)


# TEST functions
def main():
    """Test method for testing the module."""
    db = dbops.connectToDatabase("db", "stocks.db")

    if debug:
        computeAnnualDividend(db, "PPG-PREF.OL")
    else:
        c = db.cursor()
        # c.execute("""select * from stockinfo si where si.ticker like ?""", ('%' + '.OL',))
        c.execute("""select * from stockinfo si where isActive = 1""")
        items = c.fetchall()
        counter = 0
        for item in items:
            counter = counter + 1
            computeAnnualDividend(db, item[0])
            if counter % 50 == 0:
                print("Done %i of %i stocks" % (counter, len(items)))

        print("Done %i of %i stocks" % (len(items), len(items)))


if __name__ == "__main__":
    main()
