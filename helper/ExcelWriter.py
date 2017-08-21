"""ExcelWriter.py."""
import os
import os.path
import xlsxwriter
class ExcelWriter(object):

    def __init__(self):
        self.workbook = ""
        self.worksheet = ""
        self.outFile = ""


    def createWorkBook(self, cName, cPath):
        if len(cPath) > 0:
            self.outFile =  os.path.join(cPath, cName)
        else:
            self.outFile = cName
        if os.path.isfile(self.outFile):
            os.remove(self.outFile)
        self.workbook = xlsxwriter.Workbook(self.outFile)

    def addWorksheet(self, sheetName):
        self.worksheet = self.workbook.add_worksheet(sheetName)

    def writeCellData(self, cRow, cCol, cData):
        self.worksheet.write(cRow, cCol, cData)

    def addAutoFilter(self, cRow, cCol,cRowNr, cColNr):
        self.worksheet.autofilter(cRow, cCol, cRowNr, cColNr)

    def addFilter(self, cCol, cFilter):
        self.worksheet.filter_column(cCol, cFilter)

    def closeWorkBook(self):
        self.workbook.close()
