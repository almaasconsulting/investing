"""InvestmentScreenerFunctions.py"""
debug = False
def compute52WL(data, colname, colnameComp, colnameComp2,colnameComp3):
    items = data[colname].values.tolist()
    itemsComp = data[colnameComp].values.tolist()
    itemsComp2 = data[colnameComp2].values.tolist()
    dato = data[colnameComp3].values.tolist()
    resultList = []
    # GET SIZE OF data

    # print(items[2295:2298])
    try:
        # Def buy_period as last 10 days
        # Compare buy_period as last 260 days before buy_period
        start_buy = len(data.index) - 5
        end_buy = len(data.index)-1
        start_period = len(data.index) - 270
        end_period = len(data.index) - 5
        print(end_period)
        # print("Min value for buy is %f and min  value last period is %f" % (min(items[start_buy:end_buy]), min(items[start_period:end_period])))
        # print("min is %f and minperiod is %f" % (min(items[start_buy:end_buy]),
        #      min(items[start_period:end_period])))

        # print(max(items[start_buy:end_buy]))
        # print("min is: %s" % (min(items[start_buy:end_buy])))
        # print("other min is: %s" %(min(items[start_period:end_period])))
        if float(min(items[start_buy:end_buy])) < float(min(items[start_period:end_period])):
            print( itemsComp2[len(data.index)-1])
            print(min(items[start_buy:end_buy]))
            print(type(itemsComp2[len(data.index)-1]))
            print(type( float(min(items[start_buy:end_buy]))))
            if float(itemsComp2[len(data.index)-1]) > float(min(items[start_buy:end_buy])):

                # fmin(items[start_buy:end_buy]), ind pos for smallest value
                value = 10000
                item_pos = start_buy

                for pos in range(start_buy, end_buy):
                    if float(items[pos]) < float(value):
                        value = float(items[pos])
                        item_pos = pos
                datoFull = str(dato[item_pos])

                datoen = datoFull[0:-4] + "-" + datoFull[4:-2] + "-" + datoFull[-2:]

                dateCompressed = int(datoFull)
                if debug:
                    print("DatoFull is: %s" % (datoFull))
                    print("Dato is: %s" % (datoen))
                    print("DateCompressed is: %i" % (dateCompressed))
                    print("FOUND ONE!!")
                resultList.append([datoen, dateCompressed, items[item_pos]])

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        print("Error at %s" % (str(e)))
    return resultList
