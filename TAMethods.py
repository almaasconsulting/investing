"""TAMethods.py"""
debug = True

def computeGuppyMACrossOver(data, colname, MA_Low, MA_Medium, MA_High):
    # print(data.iloc[[2]])
    # values = data
    # print(data['Close'].values)
    items = data[colname].values.tolist()
    itemsMALow = data[MA_Low].values.tolist()
    itemsMAMedium = data[MA_Medium].values.tolist()
    itemsMAHigh = data[MA_High].values.tolist()
    # GET SIZE OF data
    print(len(data.index))
    # print(items)
    # print(items[2295:2298])
    pos = 0
    period = 20
    start = 0
    end = 0
    skip = 0
    antall = 0
    sum_invested = 0
    value_today = 0
    amount = 2500
    skip_period = 50
    cost = 65
    nr_of_trades = 0
    for item in items:
        if pos > period:
            end = pos
            start = pos - period
            if itemsMALow[pos] > itemsMAMedium[pos] and itemsMAMedium[pos] > itemsMAHigh[pos] and min(itemsMALow[start:end]) < min(itemsMAMedium[start:end]) and skip < 1:
                antall = antall + int(amount/items[pos])
                sum_invested = sum_invested + cost + float(int(amount/items[pos]))*items[pos]
                nr_of_trades = nr_of_trades + 1
                if debug:
                    print("Date is: " + data.iloc[[pos]][0])
                    print("Beholdning nå er: %i" % (antall))
                    print("Invested for now: %f" % sum_invested)
                skip = skip_period
        skip = skip - 1
        pos = pos + 1
    print('*'*80)
    value_today = float(antall) * items[len(data.index) - 1]
    print("Total trades performed: %i" % (nr_of_trades))
    print("Portfolio size is: %i" % (antall))
    print("Value today: %d and total invested is: %f" % (value_today, sum_invested))
    print("Gain before dividends: %2.2f percent" % ((value_today - sum_invested)*100/sum_invested))
    print('*'*80)


def computeMACrossOver(data, colname, MA_Low, MA_High):
    # print(data.iloc[[2]])
    # values = data
    # print(data['Close'].values)
    items = data[colname].values.tolist()
    itemsMALow = data[MA_Low].values.tolist()
    itemsMAHigh = data[MA_High].values.tolist()
    # GET SIZE OF data
    print(len(data.index))
    print(data)
    # print(items)
    # print(items[2295:2298])
    pos = 0
    period  = 20
    start = 0
    end = 0
    skip = 0
    antall = 0
    sum_invested = 0
    value_today = 0
    amount = 2500
    skip_period = 50
    cost = 65
    nr_of_trades = 0
    for item in items:
        if pos > period:
            end = pos
            start = pos - period
            if itemsMALow[pos] > itemsMAHigh[pos] and min(itemsMALow[start:end]) < min(itemsMAHigh[start:end]) and skip < 1:
                antall = antall + int(amount/items[pos])
                sum_invested = sum_invested + cost + float(int(amount/items[pos]))*items[pos]
                nr_of_trades = nr_of_trades + 1
                if debug:
                    print(data.iloc[[pos]])
                    print("Beholdning nå er: %i" % (antall))
                    print("Invested for now: %f" % sum_invested)
                skip = skip_period
        skip = skip - 1
        pos = pos + 1
    print('*'*80)
    value_today = float(antall) * items[len(data.index) - 1]
    gain_percent = 0
    if sum_invested > 0:
        gain_percent = (value_today - sum_invested)*100/sum_invested
    print("Total trades performed: %i" %(nr_of_trades))
    print("Portfolio size is: %i" %(antall))
    print("Value today: %d and total invested is: %f" % (value_today, sum_invested))
    print("Gain before dividends: %2.2f percent" % (gain_percent))
    print('*'*80)
    return [nr_of_trades, antall, gain_percent, sum_invested, value_today]
"""
 This function computes profit for a strategy to trade at 52 Week Low
 It is not including dividends in the strategy
"""
def compute52WLPoints(data, colname, colnameComp, colnameComp2):
    # print(data.iloc[[2]])
    # values = data
    # print(data['Close'].values)
    items = data[colname].values.tolist()
    itemsComp = data[colnameComp].values.tolist()
    itemsComp2 = data[colnameComp2].values.tolist()
    # GET SIZE OF data
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
    amount = 2500
    skip_period = 50
    cost = 65
    nr_of_trades = 0
    buy_after_days = 2
    for item in items:
        if pos > period and pos < len(data.index) - 1 - buy_after_days:
            end = pos
            start = pos - period
            if items[pos] < min(items[start:end]) and skip < 1 and itemsComp2[pos] > itemsComp[pos]:
                antall = antall + int(amount/items[pos+buy_after_days])
                sum_invested = sum_invested + cost + float(int(amount/items[pos + buy_after_days]))*items[pos+buy_after_days]
                nr_of_trades = nr_of_trades + 1
                if debug:
                    print(data.iloc[[pos]])
                    print("Before keys")
                    # print(data.keys())
                    print(data.index.values[pos+1])
                    print("After keys")
                    print("Beholdning nå er: %i" % (antall))
                    print("Invested for now: %f" % sum_invested)
                skip = skip_period
        skip = skip - 1
        pos = pos + 1
    print('*'*80)
    value_today = float(antall) * items[len(data.index) - 1]
    gain_percent = 0
    if sum_invested > 0:
        gain_percent = (value_today - sum_invested)*100/sum_invested
    print("Total trades performed: %i" %(nr_of_trades))
    print("Portfolio size is: %i" %(antall))
    print("Value today: %d and total invested is: %f" % (value_today, sum_invested))
    print("Gain before dividends: %2.2f percent" % (gain_percent))
    print('*'*80)
    return [nr_of_trades, antall, gain_percent, sum_invested, value_today]
