"""Netfonds READ companies from CSV dump."""

import csv
import urllib.request
import io

def readStockListData(url):
    stockList = []
    response = urllib.request.urlopen(url)
    cr = csv.reader(response.read().decode('iso-8859-1').splitlines())
    isFirst = True
    for row in cr:
        if isFirst:
            isFirst = False
        else:
            itemList = row[0].split('\t')
            print(itemList[1])
            stockList.append(itemList[1] + '.OL')
    print(stockList)
    return stockList

def createStockList():
    url_OAX = 'http://hopey.netfonds.no/kurs.php?exchange=OAX&sec_types=&sectors=&ticks=&table=tab&sort=alphabetic'
    url_OSE = 'http://hopey.netfonds.no/kurs.php?exchange=OSE&sec_types=&sectors=&ticks=&table=tab&sort=alphabetic'
    stockList = []
    stockList.extend(readStockListData(url_OAX))
    stockList.extend(readStockListData(url_OSE))
    return stockList
