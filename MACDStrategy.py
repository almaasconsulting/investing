import os
import io
import requests
import datetime
import pandas as pd
import pandas_datareader.data as web

"""computeMACDSTrategy.py."""
"""The purpose of this script is to compute a Margin of Safety Value
   for a stock. It should be computed based on it's chowder number
   and with it's current price and current dividend.
   t should return a fair value, a mos value and a growth potential in %.
   Could use the growth potential in rating system. This one is independendt
   from technical analysis.
"""


def computeMACDStrategy(closeSerie, fastSerie, slowSerie, openSerie, dateSerie, fast = None, slow = None, trigger = None, ticker = None):
    # CONTINUE HERE...
    debug = False
    resultList = []
    try:

        if fast is None:
            fast = 75
        if slow is None:
            slow = 100
        if trigger is None:
            trigger = 50
        if ticker is None:
            ticker = "test"

        EMAFast = closeSerie.ewm(span=fast, min_periods=fast-1, ignore_na=False,
                              adjust=True).mean()
        EMASlow = closeSerie.ewm(span=slow, min_periods=slow-1, ignore_na=False,
                              adjust=True).mean()
        MACD = pd.Series(EMAFast - EMASlow, name='MACD_%d_%d' %(fast, slow))
        EMATrigger = MACD.ewm(span=trigger, min_periods=trigger-1, ignore_na=False,
                              adjust=True).mean()


        isBuyable = True
        i = 0

        nr_of_shares = 0
        nr_of_trades = 0
        sum_cost = 0.0
        amount = 2000
        investment_cost = 29

        while i < len(MACD):

            if MACD.iloc[i] < 0 and MACD.iloc[i] < EMATrigger.iloc[i] and ((EMATrigger.iloc[i] - MACD.iloc[i])) < 1:# and (ADX[i] - NegDI[i])/NegDI[i] < 0.06:
                datoFull = str(dateSerie.iloc[i])
                datoen = datoFull[0:-4] + "-" + datoFull[4:-2] + "-" + datoFull[-2:]
                dateCompressed = int(datoFull)
                nr_of_trades = nr_of_trades + 1
                if debug:
                    print("Buy signal: MACD %f and EMATrigger: %f" %( MACD.iloc[i],  EMATrigger.iloc[i]))
                    print("DatoFull is: %s" % (datoFull))
                    print("Dato is: %s" % (datoen))
                    print("DateCompressed is: %i" % (dateCompressed))
                    print("FOUND ONE!!")

                if debug:
                    print("Dato is: %s" % (datoen))


                if(i-(len(MACD)-1)) > -1:
                    sharePrice = float(openSerie.iloc[i])
                else:
                    sharePrice = float(openSerie.iloc[i+1])

                antall = int(amount/float(sharePrice))
                nr_of_shares = nr_of_shares + antall
                sum_cost = sum_cost + float(int(amount/float(sharePrice)))* float(sharePrice) + float(investment_cost)
                totaltAntall = nr_of_shares

                resultList.append([datoen, dateCompressed, sharePrice, antall, totaltAntall])
                # i = i + 30

            i = i + 1
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)

    return resultList
