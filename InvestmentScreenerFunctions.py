"""InvestmentScreenerFunctions.py"""
debug = False
def compute52WL(data, colname, colnameComp, colnameComp2):
    items = data[colname].values.tolist()
    itemsComp = data[colnameComp].values.tolist()
    itemsComp2 = data[colnameComp2].values.tolist()
    resultList = []
    # GET SIZE OF data
    if debug:
        print(len(data.index))
    # print(items)
    # print(items[2295:2298])
    # print("IS HERE")
    try:
        # Def buy_period as last 10 days
        # Compare buy_period as last 260 days before buy_period
        start_buy = len(data.index) - 10
        end_buy = len(data.index)
        start_period = len(data.index) - 270
        end_period = len(data.index) - 10
        # print("Min value for buy is %f and min  value last period is %f" % (min(items[start_buy:end_buy]), min(items[start_period:end_period])))
        if min(items[start_buy:end_buy]) < min(items[start_period:end_period]):
            # print("Comp2 is: %f" % (itemsComp2[len(data.index)-1]))
            if itemsComp2[len(data.index)-1] > min(items[start_buy:end_buy]):
                # find pos for smallest value
                value = 10000
                item_pos = start_buy
                for pos in range(start_buy, end_buy):
                    if items[pos] < value:
                        value = items[pos]
                        item_pos = pos
                datoFull = str(data.index.values[item_pos])
                dateList = datoFull.split("T")
                dato = dateList[0]
                dateCompressed = int(dateList[0].replace("-", ""))
                if debug:
                    print(data.iloc[[pos]])
                    print(data.index.values[item_pos])
                    print("Dato is: %s" % (dato))
                    print("DateCompressed is: %i" % (dateCompressed))
                resultList.append([dato, dateCompressed, items[item_pos]])

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print(exc_type, fname, exc_tb.tb_lineno)
    return resultList
