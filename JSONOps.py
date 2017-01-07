"""Module for reading and writing json-files."""

import json
import os
from pprint import pprint

"""
Changelog:
Date:           Init:       Comment:
*******************************************************************************
17.07.2016      AA          Version 1.
"""


def readJSONFiles(jsonPath, jsonFile):
    """Method for checking if the file exists in the given path."""
    if len(jsonFile) > 0:
        # first check if jsonPath is given
        if len(jsonPath) > 0:
            # Check if it is placed in current dir or in a subdir
            try:
                open(os.path.join(os.getcwd(), jsonPath, jsonFile))
                print("Found jsonfile in working directory, or in a subfolder")
                return os.path.join(os.getcwd(), jsonPath, jsonFile)
            except IOError as e:
                print("Error: %s" % (e))
                print("""Did not find it, try to check if jsonPath is outside
                      current directory.""")
                try:
                    open(os.path.join(jsonPath, jsonFile))
                    print("""Found jsonfile in an other directory than working
                          path.""")
                    return os.path.join(jsonPath, jsonFile)
                except IOError as ee:
                    print("Error: %s" % (ee))
                    print("""Didn't find it, return error, that file not
                          exists.""")
                    return False
        else:
            # Check if it is placed in current dir or in a subdir
            try:
                open(os.path.join(os.getcwd(), jsonFile))
                print("Found jsonfile in working directory")
                return os.path.join(os.getcwd(), jsonFile)
            except IOError as e:
                print("Error: %s" % (e))
                print("""Did not find it, return error, that file not
                      exists.""")
                return False


def getListFromJSON(inDir, inFile):
    """Method for reading a json file and return a python list."""
    jsonFile = readJSONFiles(inDir, inFile)
    if jsonFile:
        with(open(readJSONFiles("infiles", "Stock.json"))) as datafile:
            data = json.load(datafile)
            return data
    else:
        print("sadfsdf")
        return False


# Creat test method for testing the yahooFinanceDataReader.
def main():
    """Test method for testing the module."""
    data = getListFromJSON("infiles", "Stock.json")
    print(data[0]['Ticker'])

if __name__ == "__main__":
    main()
