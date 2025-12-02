def fib_levels(high, low):
    diff = high - low

    return {
        "38.2": high - diff * 0.382,
        "50": high - diff * 0.50,
        "61.8": high - diff * 0.618,
        "1.2_ext": high + diff * 0.20
    }
