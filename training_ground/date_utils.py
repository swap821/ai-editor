from datetime import datetime

def days_between(start_iso, end_iso):
    start_date = datetime.fromisoformat(start_iso)
    end_date = datetime.fromisoformat(end_iso)
    delta = abs((end_date - start_date).days)
    return delta
