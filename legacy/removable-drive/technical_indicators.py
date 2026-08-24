




def obv(closes, volumes):
    """
    Calculates On-Balance Volume (OBV) for a series of prices and volumes.

    For each bar, adds volume if close > previous close, subtracts if lower, 
    and carries forward unchanged if equal. The cumulative result reveals buying 
    vs selling pressure — useful for confirming trends or spotting divergences 
    where price and volume momentum disagree.

    Args:
        closes: list of closing prices (float)
        volumes: list of trade volumes (int/float), same length as closes
    Returns:
        list of OBV values, same length as inputs.
    """

    o = [0]
    for i in range(1, len(closes)):
        o.append(o[-1] + (volumes[i] if closes[i] > closes[i-1] else -volumes[i] if closes[i] < closes[i-1] else 0))
    return o


def adl(highs, lows, closes, volumes):
    """
    Calculates the Accumulation/Distribution Line.

    For each bar, computes a Money Flow Multiplier: ((close-low) - (high-close)) / (high-low),
    which ranges from -1 (closed at low) to +1 (closed at high). Multiplied by volume gives
    Money Flow Volume, which is accumulated into a running total.

    Reveals whether a security is being accumulated (bought) or distributed (sold),
    and can diverge from price to signal upcoming reversals.

    Args:
        highs: list of high prices (float)
        lows: list of low prices (float)
        closes: list of closing prices (float)
        volumes: list of trade volumes (int/float), all same length
    Returns:
        list of ADL values, same length as inputs
    """
    result, running = [], 0
    for h, l, c, v in zip(highs, lows, closes, volumes):
        running += v * ((c - l) - (h - c)) / (h - l) if h != l else 0
        result.append(running)
    return result
