def moving_average(values, window):
    if window < 1 or window > len(values):
        raise ValueError("Window must be between 1 and the number of values")

    return [sum(values[i:i+window]) / window for i in range(len(values) - window + 1)]