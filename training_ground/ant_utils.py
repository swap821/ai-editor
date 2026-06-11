# training_ground/ant_utils.py

def trail_strength(rate, age_hours):
    return rate * (2.718 ** (-0.005 * age_hours))