"""Module for database operations."""

import os
import time
import sqlite3

"""
Changelog:
Date:           Init:       Comment:
*******************************************************************************
13.06.2016      AA          Version 1.
11.07.2016      AA          Version 1. cont. inserted initial tables with
                            start data.
"""


def checkDatabaseExists(dbDir, dbName):
    """Function for test if database exists already."""
    try:
        open(os.path.join(os.getcwd(), dbDir, dbName))
        print("DB - exists in current path")
    except IOError as e:
        print("Error: %s" % (e))
        print("DB didn't exist... Should run create database creation")
        createDatabase(dbDir, dbName, "stocks")


def connectToDatabase(dbDir, dbName):
    """Method for perform the connection to database."""
    try:
        db = sqlite3.connect(os.path.join(os.getcwd(), dbDir, dbName))
        return db
    except:
        return False


def createDatabase(dbDir, dbName, dbType):
    """Method for create the database."""
    db = sqlite3.connect(os.path.join(os.getcwd(), dbDir, dbName))
    print("------Start creating tables------")
    createTable(db, "stocks")
    createTable(db, "country")
    createTable(db, "exchange")
    createTable(db, "tainfo")
    createTable(db, "indicator")
    createTable(db, "annual_dividends")
    print("------Done creating tables------")
    print("------Start inserting default tabledata------")
    createDefaultTableValues(db)
    print("------Done creating default tabledata------")
    db.close()


def createTable(db, dbType):
    """Method for creating the different tables."""
    if dbType == "stocks":
        # Create tables for the list of stocks that the DB should contain
        c = db.cursor()
        # Continue here and creat the tables for stocks-database
        # Should be information about ticker, name, exchange, type of sector
        # country, industry etc...
        c.execute("""CREATE TABLE stockinfo (ticker text primary key,
                     name text, exchange text, category text,
                     last_change integer)
                  """)
        db.commit()
    elif dbType == "country":
        # Create table for the countries in the db.
        c = db.cursor()
        c.execute("""CREATE TABLE countries (id integer primary key,
                    name text, last_change integer)
                  """)
        db.commit()
    elif dbType == "exchange":
        # Create table for the exchanges in the db
        c = db.cursor()
        c.execute("""CREATE TABLE exchange (id integer primary key,
                    name text, last_change integer)
                  """)
        db.commit()
    elif dbType == "tainfo":
        # Create the table for storing tainfo about a stock
        c = db.cursor()
        c.execute("""CREATE TABLE tainfo (ticker text, indicator_id integer,
                     value real, last_change integer,
                     primary key(ticker, indicator_id))
                  """)
        db.commit()
    elif dbType == "indicator":
        # Create the table for storing tainfo about a stock
        c = db.cursor()
        c.execute("""CREATE TABLE indicator (id integer primary key,
                     name text, description text, last_change integer)
                  """)
        db.commit()
    elif dbType == "annual_dividends":
        # Create table for the annual dividendes for stocks in the database
        # Should be information about id, that should match id in the stocks
        # table(in case of a stock change its ticker symbol)
        c = db.cursor()
        c.execute("""CREATE TABLE annual_dividends (ticker text,
                      year integer, dividends real, nr_of_periods integer,
                      last_change integer, primary key(ticker, year))
                 """)
        db.commit()
    elif dbType == "fainfo":
        c = db.cursor()
        c.execute("""CREATE TABLE fainfo (ticker text, name text,
                  paramValue real, last_change integer,
                  primary key(ticker, name))""")
        db.commit()


def createDefaultTableValues(db):
    """Method for creating default values in table."""
    # Function for inserting standard values in the database
    # Start with indicators - MA 3,5,8,10,12,15 (SHORT TERM)
    #                         MA 30,35,40,45,50,60 (LONG TERM)
    inserttime = time.time()
    values = [(0, "3 EMA", "3-days EMA", inserttime),
              (1, "5 EMA", "5-days EMA", inserttime),
              (2, "8 EMA", "8-days EMA", inserttime),
              (3, "10 EMA", "10-days EMA", inserttime),
              (4, "12 EMA", "12-days EMA", inserttime),
              (5, "15 EMA", "15-days EMA", inserttime),
              (6, "30 EMA", "30-days EMA", inserttime),
              (7, "35 EMA", "35-days EMA", inserttime),
              (8, "40 EMA", "40-days EMA", inserttime),
              (9, "45 EMA", "45-days EMA", inserttime),
              (10, "50 EMA", "50-days EMA", inserttime),
              (11, "60 EMA", "60-days EMA", inserttime)]
    c = db.cursor()
    c.executemany("""insert into indicator values(?,?,?,?)""", values)
    db.commit()

# TEST AREA
checkDatabaseExists("db", "test.db")
