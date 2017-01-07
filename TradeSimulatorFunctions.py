"""TradeSimulatorFunctions.py"""
debug = False
def compute52WLTrades(data, colname, colnameComp, colnameComp2):
    items = data[colname].values.tolist()
    itemsComp = data[colnameComp].values.tolist()
    itemsComp2 = data[colnameComp2].values.tolist()
    resultList = []

    # GET SIZE OF data
    if debug:
        print(len(data.index))
    # print(items)
    # print(items[2295:2298])
    pos = 0
    period  = 100
    start = 0
    end = 0
    skip = 0
    antall = 0
    sum_invested = 0
    value_today = 0
    amount = 2000
    skip_period = 50
    cost = 65
    nr_of_trades = 0
    buy_after_days = 1
    try:
        for item in items:
            if pos > period and pos < len(data.index) - 1 - buy_after_days:
                end = pos
                start = pos - period
                if items[pos] < min(items[start:end]) and skip < 1 and itemsComp2[pos] > itemsComp[pos]:
                    antall = antall + int(amount/items[pos+buy_after_days])
                    sum_invested = sum_invested + cost + float(int(amount/items[pos + buy_after_days]))*items[pos+buy_after_days]
                    nr_of_trades = nr_of_trades + 1
                    datoFull = str(data.index.values[pos+buy_after_days])
                    dateList = datoFull.split("T")
                    dato = dateList[0]
                    dateCompressed = int(dateList[0].replace("-", ""))
                    if debug:
                        print(data.iloc[[pos]])
                        print("Beholdning nå er: %i" % (antall))
                        print("Invested for now: %f" % sum_invested)
                        print(data.index.values[pos+buy_after_days])
                        print("Dato is: %s" % (dato))
                        print("DateCompressed is: %i" % (dateCompressed))
                    resultList.append([dato, dateCompressed, items[pos + buy_after_days], int(amount/items[pos+buy_after_days]),antall ])

                    skip = skip_period
            skip = skip - 1
            pos = pos + 1
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)
    return resultList


def computeMACrossOver(data, colname, MA_Low, MA_High):
    # print(data.iloc[[2]])
    # values = data
    # print(data['Close'].values)
    items = data[colname].values.tolist()
    itemsMALow = data[MA_Low].values.tolist()
    itemsMAHigh = data[MA_High].values.tolist()
    resultList = []
    # GET SIZE OF data
    if debug:
        print(len(data.index))
        print(data)
    pos = 0
    period  = 100
    start = 0
    end = 0
    skip = 0
    antall = 0
    sum_invested = 0
    value_today = 0
    amount = 2000
    skip_period = 50
    cost = 65
    nr_of_trades = 0
    buy_after_days = 1
    try:
        for item in items:
            if pos > period:
                end = pos
                start = pos - period
                if itemsMALow[pos] > itemsMAHigh[pos] and min(itemsMALow[start:end]) < min(itemsMAHigh[start:end]) and skip < 1:
                    antall = antall + int(amount/items[pos+buy_after_days])
                    sum_invested = sum_invested + cost + float(int(amount/items[pos + buy_after_days]))*items[pos+buy_after_days]
                    nr_of_trades = nr_of_trades + 1
                    datoFull = str(data.index.values[pos+buy_after_days])
                    dateList = datoFull.split("T")
                    dato = dateList[0]
                    dateCompressed = int(dateList[0].replace("-", ""))
                    if debug:
                        print(data.iloc[[pos]])
                        print("Beholdning nå er: %i" % (antall))
                        print("Invested for now: %f" % sum_invested)
                        print(data.index.values[pos+buy_after_days])
                        print("Dato is: %s" % (dato))
                        print("DateCompressed is: %i" % (dateCompressed))
                    resultList.append([dato, dateCompressed, items[pos + buy_after_days], int(amount/items[pos+buy_after_days]),antall])
                    skip = skip_period
            skip = skip - 1
            pos = pos + 1
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)
    return resultList
