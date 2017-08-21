"""FTPTransfer.py."""

from ftplib import FTP
import traceback


def createFTPConnection(host, user, pwd):
    """Function for creating a connection to a ftp-server.
       Input is host - server to connect to
                user - username
                pwd  - password
       Return: a ftp connection or False
    """
    try:
        port = 21
        # print("host: %s -- user: %s --  pwd %s" % (host, user, pwd))
        ftp = FTP(host)
        ftp.login(user, pwd)
    except:
        print("Something wrong happened")
        ftp = False
    finally:
        return ftp

def testConnection(ftp):
    print("File List")
    ftp.cwd("/SPA/")
    files = ftp.dir()
    print(files)


def ftpUploadBinary(ftp, file2Upload):
    try:
        ftp.cwd("/FTP/Data/")
        f = open(file2Upload, "rb")
        name = str(file2Upload.split("/")[len(file2Upload.split("/"))-1] )
        ftp.storbinary('STOR ' + name, f)
        f.close()
    except:
        traceback.print_exc()


def closeConnection(ftp):
    ftp.quit()


# Creat test method for testing the yahooFinanceDataReader.
def main():
    """Test method for testing the module."""
    ftp = createFTPConnection("ftp.dividendgrowth.no", "dividendgrowth.no", "Al10maas!")
    # testConnection(ftp)
    file2Upload = "SVG/FRO.OL_chart.svg"
    ftpUploadBinary(ftp, file2Upload)
    closeConnection(ftp)


if __name__ == "__main__":
    main()
