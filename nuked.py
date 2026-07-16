# Have we been nuked yet?
# Compares each EPA RadNet monitor's latest gamma count rate to its own
# baseline (mean and standard deviation) for the year. A reading far above
# a station's normal variation = bad news.
# Usage:  python nuked.py            (sweep monitors across the country)
#         python nuked.py CO DENVER  (check a single monitor)
# Exit codes: 0 all normal, 1 possible spill, 2 possible nuke, 3 no data.

import argparse
import csv
import datetime
import io
import statistics
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# Stations verified to have current data, spread across the US.
STATIONS = [
    ("AK", "ANCHORAGE"), ("AL", "BIRMINGHAM"), ("AZ", "PHOENIX"),
    ("CA", "LOS ANGELES"), ("CA", "SAN FRANCISCO"), ("CO", "DENVER"),
    ("DC", "WASHINGTON"), ("FL", "MIAMI"), ("GA", "ATLANTA"),
    ("HI", "HONOLULU"), ("IL", "CHICAGO"), ("MA", "BOSTON"),
    ("MI", "DETROIT"), ("MN", "ST. PAUL"), ("MO", "ST. LOUIS"),
    ("NV", "LAS VEGAS"), ("NY", "ALBANY"), ("OR", "PORTLAND"),
    ("PA", "PHILADELPHIA"), ("TX", "AUSTIN"), ("UT", "SALT LAKE CITY"),
    ("WA", "SEATTLE"),
]

COUNT_COLUMNS = ["GAMMA COUNT RATE R0%d (CPM)" % n for n in range(2, 10)]

# A spill must be BOTH far outside the station's normal variation
# (many standard deviations) AND meaningfully above its mean — the
# second condition stops a hyper-stable station from panicking over
# a tiny blip. Ten times the mean means catastrophe, full stop.
SPILL_SIGMAS = 10.0
SPILL_RATIO = 1.5
NUKE_RATIO = 10.0

# RadNet monitors usually report within a couple of hours. Longer
# silence means the monitor is down... which is not reassuring.
STALE_HOURS = 6


def download_year(state, city, year):
    url = "https://radnet.epa.gov/cdx-radnet-rest/api/rest/csv/%d/fixed/%s/%s" % (
        year, state, city.replace(" ", "%20"))
    with urllib.request.urlopen(url, timeout=30) as response:
        text = response.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def fetch_rows(state, city):
    year = datetime.date.today().year
    rows = download_year(state, city, year)
    if not rows:
        # Early January: this year's file barely exists yet, so fall
        # back to last year's data for a usable baseline.
        rows = download_year(state, city, year - 1)
    return rows


def total_count(row):
    values = [float(row[col]) for col in COUNT_COLUMNS if row[col] != ""]
    if not values:
        return None
    return sum(values)


def hours_old(timestamp, now):
    then = datetime.datetime.strptime(timestamp, "%m/%d/%Y %H:%M:%S")
    return (now - then).total_seconds() / 3600


def assess(latest, mean, std):
    if mean <= 0:
        return "UNKNOWN"
    ratio = latest / mean
    if ratio >= NUKE_RATIO:
        return "NUKE"
    if std > 0:
        sigmas = (latest - mean) / std
    else:
        # A station that reported the same value all year: any rise at
        # all is infinitely surprising, so let the ratio test decide.
        sigmas = float("inf") if latest > mean else 0.0
    if sigmas >= SPILL_SIGMAS and ratio >= SPILL_RATIO:
        return "SPILL"
    return "NORMAL"


def check_station(state, city):
    try:
        rows = fetch_rows(state, city)
    except urllib.error.URLError as error:
        raise ValueError("download failed: %s" % getattr(error, "reason", error))
    totals = [t for t in (total_count(row) for row in rows) if t is not None]
    if not totals:
        raise ValueError("no data - check the spelling, station names are like 'SALT LAKE CITY'")
    mean = statistics.fmean(totals)
    std = statistics.pstdev(totals)
    # RadNet timestamps are GMT, so compare against GMT "now".
    age = hours_old(rows[-1]["SAMPLE COLLECTION TIME"], datetime.datetime.utcnow())
    return {
        "station": "%s, %s" % (city, state),
        "latest": totals[-1],
        "ratio": totals[-1] / mean,
        "verdict": assess(totals[-1], mean, std),
        "age": age,
    }


def sweep(stations):
    results, failures = [], []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(check_station, s, c): (s, c) for s, c in stations}
        for future, (state, city) in futures.items():
            try:
                results.append(future.result())
            except ValueError as error:
                failures.append("%s, %s: %s" % (city, state, error))

    results.sort(key=lambda r: r["ratio"], reverse=True)
    for r in results:
        note = "  ** silent for %.0f hours" % r["age"] if r["age"] > STALE_HOURS else ""
        print("%-22s %8.0f cpm  %5.2fx normal  %-7s%s" % (
            r["station"], r["latest"], r["ratio"], r["verdict"], note))
    for f in failures:
        print("FAILED: %s" % f)

    verdicts = [r["verdict"] for r in results]
    stale = [r for r in results if r["age"] > STALE_HOURS]
    if "NUKE" in verdicts:
        print("\nHAVE WE BEEN NUKED? ...possibly?! A monitor is reading catastrophic levels!")
        return 2
    if "SPILL" in verdicts:
        print("\nNo nuke, BUT a monitor is far outside its normal range. Spill? Check the news.")
        return 1
    if not results:
        print("\nEvery monitor failed. Either the internet is down... or, uh oh.")
        return 3
    word = "monitor is" if len(results) == 1 else "monitors are"
    print("\nHAVE WE BEEN NUKED? No. All %d %s near normal levels." % (len(results), word))
    if stale:
        print("(Though %d of them went quiet more than %d hours ago. Probably maintenance. Probably.)"
              % (len(stale), STALE_HOURS))
    return 0


def main():
    parser = argparse.ArgumentParser(description="Have we been nuked yet?")
    parser.add_argument("state", nargs="?", help="two-letter state code, e.g. CO")
    parser.add_argument("city", nargs="?", help="monitor city name, e.g. DENVER")
    args = parser.parse_args()

    if args.state and not args.city:
        parser.error("give both a state and a city, e.g.: python nuked.py CO DENVER")
    if args.state:
        code = sweep([(args.state.upper(), args.city.upper())])
    else:
        print("Checking %d monitors across the country...\n" % len(STATIONS))
        code = sweep(STATIONS)
    sys.exit(code)


if __name__ == "__main__":
    main()
