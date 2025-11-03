# src/tools/web.py
import requests, csv, io

# Example source: a capitals list with coords (verify against NE or Wikipedia as needed).
CAPITALS_CSV = "https://gist.githubusercontent.com/ofou/df09a6834a8421b4f376c875194915c9/raw/country-capital-lat-long-population.csv"

def load_capitals():
    r = requests.get(CAPITALS_CSV, timeout=20)
    r.raise_for_status()
    reader = csv.reader(io.StringIO(r.text))
    rows = []
    for row in reader:
        if len(row) < 5: 
            continue
        country, capital, lat, lon = row[0].strip(), row[1].strip(), float(row[2]), float(row[3])
        rows.append((country, capital, lat, lon))
    return rows
