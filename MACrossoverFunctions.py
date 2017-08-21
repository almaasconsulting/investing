"""
 This function computes profit for a strategy to trade at 52 Week Low
 It is not including dividends in the strategy
"""
debug = True


def computeMACrossOver(data, MA_Low, MA_High):
    items = data.values.tolist()
    itemsMALow = MA_Low
    itemsMAHigh = MA_High
    resultList = []

    # GET SIZE OF data
    if debug:
        print(len(MA_Low))
    # print(items)
    # print(items[2295:2298])
    pos = 0
    period = 100
    start = 0
    end = 0
    skip = 0
    antall = 0
    sum_invested = 0
    amount = 2000
    skip_period = 50
    cost = 45
    nr_of_trades = 0
    buy_after_days = 1
    try:
        for item in items:
            if pos > period and pos < len(items) - 1 - buy_after_days:
                end = pos
                start = pos - period
                if items[pos] < min(items[start:end]) and skip < 1 and itemsMAHigh[pos] > itemsMALow[pos]:
                    antall = antall + int(amount/items[pos+buy_after_days])
                    sum_invested = sum_invested + cost + float(int(amount/items[pos + buy_after_days]))*items[pos+buy_after_days]
                    nr_of_trades = nr_of_trades + 1
                    datoFull = str(data.index.values[pos+buy_after_days])
                    dateList = datoFull.split("T")
                    dato = dateList[0]
                    dateCompressed = int(dateList[0].replace("-", ""))
                    resultList.append([dato, dateCompressed, items[pos + buy_after_days],
                                       int(amount/items[pos+buy_after_days]), sum_invested, antall])
                    skip = skip_period
            skip = skip - 1
            pos = pos + 1
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)
    return resultList
