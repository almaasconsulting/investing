"""MarginOfSafetyCalculator.py."""
"""The purpose of this script is to compute a Margin of Safety Value
   for a stock. It should be computed based on it's chowder number
   and with it's current price and current dividend.
   t should return a fair value, a mos value and a growth potential in %.
   Could use the growth potential in rating system. This one is independendt
   from technical analysis.
"""

def computeMarginOfSafety(cLastClose, cDiv, cDivYield,cDivGrowth):
    # print("Values: %f, %f, %f, %f" % (cLastClose, cDiv, cDivYield, cDivGrowth))
    values = []
    factor = 0.09

    if cDivYield > 1:
        cDivYield = round(float(cDivYield / 100.0),2)
    if cDivGrowth > 1:
        cDivGrowth = round(float(cDivGrowth / 100.0),2)
    if cDivYield > 0.1:
        factor = 0.09
    elif cDivYield > 0.06:
        factor = 0.07
    else:
        factor = cDivYield

    mosFactor = 0.8
    fairValue = cDiv *(1 + cDivGrowth)/(factor)
    mos = fairValue * mosFactor
    growthPotential = (fairValue - cLastClose)/cLastClose
    values = [fairValue, mos, growthPotential]
    return values

# TEST functions
def main():
    """Test method for testing the module."""
    mosData = computeMarginOfSafety(5.51, 0.6, 10.89,3.71)
    print(mosData)


if __name__ == "__main__":
    main()
