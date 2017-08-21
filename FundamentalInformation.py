"""Module for FundamentalInformation."""
import time
from datetime import date
import urllib.request
import pandas as pd
# User generated modules
import YahooDataReader as ydr
import databaseOPS as dbops
from FTP import FTPTransfer as ft



"""This module should generate fundamental information for a given stock or
   a list of stocks, maybe test with 50 for increased performance, and have
   a break for each time to not overload the yahoo server and get banned.
   The module should send the ticker(s) of interest to YahooDataReader.py and
   with "fundamental" as type. Should get a list of data, one row for each
   ticker. For each row, and for each element create a values array and
   perform executemany query. One for each row, commit after each insert.
   Maybe executemany on all rows at one time.. See if possible could be
   a big list. One row ind fundamentalinfo - table for each fundamental
   parameter for each stock. Remove "N/A"'s => more easy to filter on list..

Changelog:
Date:           Init:       Comment:
*******************************************************************************
30.07.2016      AA          Version 1.
"""
# Start with fetching all the stocks from stockinfo database, maybe remove some
# To save time and they wouldn't be of any interest anyway.
# Take 10 and 10 stocks call YahooDataReader with fundamental as type.
# Whern result come, build the query paramater as an array of arrays and
# perform an executemany. At each 200 take a 5 second break to not pressure
# the server

debug = False


def insertFundamentalData(db):
    """Given a db connection, start fetching all the tickers of interest."""
    c = db.cursor()
    query = """select * from stockinfo si where (instr(si.ticker, '.OL') or
               instr(si.ticker, '.TO') or instr(si.ticker, '.V') or
               instr(si.ticker, '.L') or instr(si.ticker, '.IL') or
               not instr(si.ticker, '.')) and si.ticker in
               (select ad.ticker from annual_dividends ad where ad.year > 2014)
               and si.isActive > 0"""
    # query = """select * from stockinfo si where (instr(si.ticker, '.OL')) and si.isActive = 1"""
    c.execute(query)
    faData = []
    today = date.today()
    dato = int(str(today).replace("-", ""))
    data = c.fetchall()
    antall = 100
    counter = 0
    tickers = []
    antall_ferdig = 0
    totalt = len(data)
    for item in data:
        antall_ferdig = antall_ferdig + 1
        if antall_ferdig > 499:
            if antall_ferdig % 500 < 1:
                csv_df = pd.DataFrame(faData)
                file2Upload = "fainfo.csv"
                csv_df.to_csv(file2Upload, index=False, header=False)
                ftpConn = ft.createFTPConnection("ftp.dividendgrowth.no", "dividendgrowth.no", "Al10maas!")
                ft.testConnection(ftpConn)
                ft.ftpUploadBinary(ftpConn, file2Upload)
                ft.closeConnection(ftpConn)
                # Process file on server
                with urllib.request.urlopen("http://dividendgrowth.no/modules/UpdateFAInfo.php?file=" + file2Upload) as response:
                    html = response.read()
                faData = []
        if counter > antall:
            if debug:
                print("Start sleep")
            time.sleep(5)
            if debug:
                print("End sleep")
            # print(item[0])
            tickers.append(item[0])
            # print(tickers)
            parameters = ['s', 'n', 'y', 'p', 'k', 'j', 'k5', 'j6', 'e', 'e7',
                          'e8', 't8', 'b4', 'p5', 'p6', 'r', 'r5', 'r6', 'r7',
                          'm6', 'm8', 'd']
            faInfo = ydr.yahooFinanceDataReader(tickers, [], parameters,
                                                'fundamental')
            if debug:
                print(faInfo)
            inserttime = time.time()
            if faInfo:
                # Start iterate through all items
                for item in faInfo:
                    # get ticker, start with deleting all values for this
                    # ticker
                    ticker = item[0]
                    c.execute("""delete from fainfo where ticker = ?""",
                              (ticker,))
                    db.commit()
                    # now create an array of inserts for each variable
                    # should strip of any -, + %
                    # y = dividend yield
                    teller = 0
                    values = []
                    paramValues = []
                    for element in item:
                        if teller > 1:
                            # print("indicator is: %s and value is: %s"
                            #      % (parameters[teller], element))
                            nogos = ["N/A", float('Inf'), '0.00']
                            if element not in nogos:
                                # First remove %
                                val_percent = element.strip().split("%")[0]
                                # remove +
                                val_plusList = val_percent.strip().split("+")
                                val_plus = val_plusList[len(val_plusList)-1]
                                # remove -
                                val_minusList = val_plus.strip().split("-")
                                val_minus = val_minusList[len(val_minusList)-1]
                                factor = 1
                                if len(val_minusList) > 1:
                                    factor = -1
                                value = float(val_minus.strip())*factor
                                if float(value) != float('Inf'):
                                    paramValues = [ticker, parameters[teller],
                                                   value, inserttime]
                                    # print(paramValues)
                                    faData.append([ticker, parameters[teller], value, dato])
                                    values.append(paramValues)
                        teller = teller + 1
                    c.executemany("""insert into fainfo values(?,?,?,?)""",
                                  values)
                    db.commit()

                    counter = 0
                    tickers = []
            print("Finished with %i of %i" % (antall_ferdig, totalt))
        else:
            tickers.append(item[0])
        counter = counter + 1
    print("Done with %i of %i" % (totalt, totalt))
    # Now create the file for webpage
    csv_df = pd.DataFrame(faData)
    file2Upload = "fainfo.csv"
    csv_df.to_csv(file2Upload, index=False, header=False)
    ftpConn = ft.createFTPConnection("ftp.dividendgrowth.no", "dividendgrowth.no", "Al10maas!")
    ft.testConnection(ftpConn)
    ft.ftpUploadBinary(ftpConn, file2Upload)
    ft.closeConnection(ftpConn)
    # Process file on server
    with urllib.request.urlopen("http://dividendgrowth.no/modules/UpdateFAInfo.php?file=" + file2Upload) as response:
        html = response.read()

# TEST functions
def main():
    """Test method for testing the module."""
    db = dbops.connectToDatabase("db", "stocks.db")
    insertFundamentalData(db)


if __name__ == "__main__":
    main()
