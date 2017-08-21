"""Compute the Chowder number for a given stock."""
import databaseOPS as dbops
from helper import ExcelWriter
import MarginOfSafetyCalculator as mosc
"""The following is the rules for computing the chowder number:
    if divyield > 3%
       sum of divyield and 5year divgrowt > 12%
    if divyield < 3%
       sum of divyield and 5year divgrowt > 15%
    if stockIsUtility
       sum of divyield and 5year divgrowt > 8%
"""
"""Strategy to compute the chowder number:
    1. First fill the database with dividend data for the different companies.
    2. Update last close price
    3. Compute current div. yield by taking last year dividends and divide
       by the last close price(Adjust with currency if dividend is in
       $ and not in NOK.)
    4. Compute the dividend growth for the stock by getting the dividend for the
       last year,(not this one) and go 3 to 5 year back(if it exists) and
       find the growth factor by using the following formula

       Query to run for fetching the following info:
        - ticker
        - last close
        - year new
        - dividends new
        - year old
        - dividends old
        - growth period (new - old)
        - nr of years registered dividends
        - current yield

        select ad_new.ticker, fi.paramValue,ad_new.year,ad_new.dividends,
        ad_old.year,ad_old.dividends, (ad_new.dividends/ad_old.dividends) * 100
        as 'growth period year' ,(select count(dividends) from annual_dividends
        where ticker = ad_new.ticker group by ticker) as antall,
        round(ad_new.dividends/fi.paramValue*100,2) as 'Curr_yield'
        from annual_dividends ad_new
        inner join annual_dividends ad_old on ad_old.ticker = ad_new.ticker
        inner join fainfo fi on fi.ticker = ad_new.ticker
        where
        ad_new.year = 2016
        and ad_old.year = 2011
        and ad_new.dividends > ad_old.dividends
        and (ad_new.dividends/ad_old.dividends) * 100  > 100
        and fi.name = 'p'
        order by antall desc,  (ad_new.dividends/ad_old.dividends)  desc

        From this query chowder number can be computed. Then a list of intersting
        candidates can be given for further analysis.


"""
debug = False
def computeChowderNumber(db, start, end):
    c = db.cursor()
    # c.execute("""select * from stockinfo si where si.ticker like ?""", ('%' + '.OL',))
    c.execute("""select ad_new.ticker, fi.paramValue,ad_new.year,ad_new.dividends,
    ad_old.year,ad_old.dividends, (ad_new.dividends/ad_old.dividends)
    as 'growth period year' ,(select count(dividends) from annual_dividends
    where ticker = ad_new.ticker group by ticker) as antall,
    round(ad_new.dividends/fi.paramValue*100,2) as 'Curr_yield'
    from annual_dividends ad_new
    inner join annual_dividends ad_old on ad_old.ticker = ad_new.ticker
    inner join fainfo fi on fi.ticker = ad_new.ticker
    where (instr(ad_new.ticker, '.OL') or
    instr(ad_new.ticker, '.TO') or instr(ad_new.ticker, '.V') or
    instr(ad_new.ticker, '.L') or instr(ad_new.ticker, '.IL') or
     not instr(ad_new.ticker, '.'))
    and ad_old.year = ?
    and ad_new.year = ?
    and ad_new.dividends > ad_old.dividends
    and (ad_new.dividends/ad_old.dividends)
    and fi.name = 'p'
    order by antall desc,  (ad_new.dividends/ad_old.dividends)  desc""", [start, end])

    test = ExcelWriter.ExcelWriter()
    test.createWorkBook("Chowder_"+str(start)+"_"+str(end)+".xlsx", "db")
    test.addWorksheet("chowder")
    row = 0
    col = 0
    test.writeCellData(row,col, "Stock")
    test.writeCellData(row, col + 1, "Start year")
    test.writeCellData(row, col + 2, "End year")
    test.writeCellData(row, col + 3, "Last close")
    test.writeCellData(row, col + 4, "Curr. div.yield")
    test.writeCellData(row,col + 5, "Dividend growth")
    test.writeCellData(row, col + 6, "Chowder")
    test.writeCellData(row, col + 7, "Nr year with dividends")
    items = c.fetchall()
    counter = 0
    toHighs = []
    counter_low = 0
    chowderCount = 0
    print("Got a list of stocks with data, start computing the chowder number")
    for item in items:
        if debug:
            print(item)
        # Should compute the chowder number and print if > 8%
        chowder_part = round((pow(float(item[3]/item[5]),1/(end-start + 1))-1)*100,2)
        chowder = chowder_part + float(item[8])
        isOK = False
        if chowder > 8 and  chowder < 30:
            if float(item[8]) > 3 and chowder > 12:
                isOK = True
            if float(item[8]) < 3.01 and chowder > 15:
                isOK = True
            if isOK:
                row = row + 1
                print(item)
                print("Stock %s has chowder %f and divyield at %f" % (item[0], chowder,  float(item[8]) ))
                test.writeCellData(row,col, item[0])
                test.writeCellData(row, col + 1, start)
                test.writeCellData(row, col + 2, end)
                test.writeCellData(row, col + 3, float(item[1]))
                test.writeCellData(row, col + 4, float(item[8]))
                test.writeCellData(row,col + 5, chowder_part)
                test.writeCellData(row, col + 6, chowder)
                test.writeCellData(row, col + 7, item[7])
                counter_low = counter_low + 1
                chowderCount = chowderCount + 1
        elif chowder > 30:
            toHighs.append([item[0], start, end, float(item[1]), float(item[8]), chowder_part, chowder, item[7]])
        counter = counter + 1
        if counter % 50 == 0:
            print("Done %i of %i stocks" % (counter, len(items)))
    test.addAutoFilter(0,0,counter_low,7)
    print("Now done iterating the list, now add a new sheet to store info about the chowder values with to high chowder")
    test.addWorksheet("high-chowder")
    row = 0
    col = 0
    test.writeCellData(row,col, "Stock")
    test.writeCellData(row, col + 1, "Start year")
    test.writeCellData(row, col + 2, "End year")
    test.writeCellData(row, col + 3, "Last close")
    test.writeCellData(row, col + 4, "Curr. div.yield")
    test.writeCellData(row, col + 5, "Dividend growth")
    test.writeCellData(row, col + 6, "Chowder")
    test.writeCellData(row, col + 7, "Nr year with dividends")
    for item in toHighs:
        row = row + 1
        test.writeCellData(row,col, item[0])
        test.writeCellData(row, col + 1, item[1])
        test.writeCellData(row, col + 2, item[2])
        test.writeCellData(row, col + 3, item[3])
        test.writeCellData(row, col + 4, item[4])
        test.writeCellData(row, col + 5, item[5])
        test.writeCellData(row, col + 6, item[6])
        test.writeCellData(row, col + 7, item[7])

    print("Done %i of %i stocks" % (len(items), len(items)))
    print("Found %i of %i stocks that has a chowder > 8 percent" %
         (chowderCount, len(items)))
    test.addAutoFilter(0,0,len(toHighs),7)
    # test.addFilter(5, "x > 7")
    # test.addFilter(10,"x > 0.06")

def computeChowderNumberForStock(db, start, end, cStock):
    debug = False
    c = db.cursor()
    # c.execute("""select * from stockinfo si where si.ticker like ?""", ('%' + '.OL',))
    c.execute("""select ad_new.ticker, fi.paramValue,ad_new.year,ad_new.dividends,
    ad_old.year,ad_old.dividends, (ad_new.dividends/ad_old.dividends)
    as 'growth period year' ,(select count(dividends) from annual_dividends
    where ticker = ad_new.ticker group by ticker) as antall,
    round(ad_new.dividends/fi.paramValue*100,2) as 'Curr_yield',
    strftime('%d.%m.%Y', datetime(fi.last_change,'unixepoch'))
    from annual_dividends ad_new
    inner join annual_dividends ad_old on ad_old.ticker = ad_new.ticker
    inner join fainfo fi on fi.ticker = ad_new.ticker
    where ad_new.ticker = ?
    and ad_old.year = ?
    and ad_new.year = ?
    and ad_new.dividends > ad_old.dividends
    and (ad_new.dividends/ad_old.dividends) > 1
    and fi.name = 'p'""", [cStock, start, end])
    # Fetch data from the executed query. Should only be one result.
    items = c.fetchall()
    isOK = False
    chowderType = ""
    values = []
    if debug:
        print("Got the data for stock %s, start computing the chowder number" % (cStock))
    for item in items:
        # Should compute the chowder number and print if > 8%
        chowder_part = round((pow(float(item[3]/item[5]),1/(end-start + 1))-1)*100,2)
        chowder = chowder_part + float(item[8])
        chowderType = ""
        if chowder > 8 and  chowder < 30:
            if float(item[8]) > 3 and chowder > 12:
                isOK = True
                chowderType = "High Yield - Chowder > 12"
            if float(item[8]) < 3.01 and chowder > 15:
                chowderType = "Low Yield - Chowder > 15"
                isOK = True
        elif chowder > 30:
            if float(item[8]) > 3:
                chowderType = "High Yield - Chowder > 30"
            if float(item[8]) < 3.01:
                chowderType = "Low Yield - Chowder > 30"
            isOK = True
        else:
            isOK = False
        values = [isOK, chowderType, chowder, chowder_part, float(item[8]), float(item[1]), item[9]]
    return values

# TEST functions
def main():
    """Test method for testing the module."""
    db = dbops.connectToDatabase("db", "stocks.db")
    # computeChowderNumber(db,2011,2016)
    chowData = computeChowderNumberForStock(db, 2011, 2016, "MSI")
    print(chowData)


if __name__ == "__main__":
    main()
