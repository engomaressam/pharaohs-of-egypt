"""Step 2: turn the raw Wikidata rows into clean, validated tables.

  data/pharaohs.csv   one row per pharaoh: name, Wikidata id, dynasty, period, reign start/end (BC/AD years, with
                      the precision Wikidata records), birth, death, sex, image and Wikipedia URLs
  data/dynasties.csv  one row per dynasty: Wikidata's dates where it has them, plus the conventional chronology
                      from data/reference/dynasties_conventional.csv (Shaw 2000) joined by dynasty number
  data/pyramids.csv   one row per pyramid: coordinates, height, the pharaoh it was built for, place, date

Dates: Wikidata stores years in astronomical numbering (year 0 exists), so -1549 means 1550 BC. `*_year`
columns are signed astronomical years (negative = BC); `*_label` columns are human-readable ("1550 BC").
Precision 9 = year, 8 = decade, 7 = century, 11 = day. A pharaoh with several position statements keeps the
earliest start and the latest end. Validation is in validate.py and runs at the end of this script.
"""
import json, re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT = ROOT / "data" / "raw", ROOT / "data"
PRECISION = {11: "day", 10: "month", 9: "year", 8: "decade", 7: "century", 6: "millennium"}
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
            "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17,
            "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "twenty-first": 21, "twenty-second": 22, "twenty-third": 23,
            "twenty-fourth": 24, "twenty-fifth": 25, "twenty-sixth": 26, "twenty-seventh": 27, "twenty-eighth": 28, "twenty-ninth": 29,
            "thirtieth": 30, "thirty-first": 31}


def v(row, key):
    return row[key]["value"] if key in row else None


def qid(uri):
    return uri.rsplit("/", 1)[1] if uri else None


def astro_year(ts):
    """'-1549-01-01T00:00:00Z' -> -1549 ; '0030-01-01T00:00:00Z' -> 30"""
    if not ts:
        return None
    m = re.match(r"([+-]?\d+)-", ts)
    return int(m.group(1)) if m else None


def year_label(y):
    if y is None or pd.isna(y):
        return None
    y = int(y)
    return f"{1 - y} BC" if y <= 0 else f"AD {y}"


def dynasty_number(label):
    if not isinstance(label, str) or not label:
        return None
    s = label.lower()
    if s.startswith("dynasty 0"):
        return 0
    for word, n in ORDINALS.items():
        if s.startswith(word + " dynasty"):
            return n
    if "ptolemaic" in s:
        return 33
    if "argead" in s or "macedonian" in s:
        return 32
    return None


def build_pharaohs():
    rows = json.load(open(RAW / "pharaohs.json", encoding="utf-8"))
    recs = []
    for r in rows:
        recs.append({"wikidata_id": qid(v(r, "pharaoh")), "name": v(r, "pharaohLabel"), "description": v(r, "pharaohDescription"),
                     "dynasty_id": qid(v(r, "dynasty")), "dynasty": v(r, "dynastyLabel"),
                     "reign_start_year": astro_year(v(r, "start")), "reign_start_precision": PRECISION.get(int(v(r, "startPrecision") or 0)),
                     "reign_end_year": astro_year(v(r, "end")), "reign_end_precision": PRECISION.get(int(v(r, "endPrecision") or 0)),
                     "birth_year": astro_year(v(r, "birth")), "death_year": astro_year(v(r, "death")), "sex": v(r, "sexLabel"),
                     "image_url": v(r, "image"), "wikipedia_url": v(r, "article")})
    df = pd.DataFrame(recs)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)]           # items without an English label
    agg = {"name": "first", "description": "first", "dynasty_id": "first", "dynasty": "first",
           "reign_start_year": "min", "reign_start_precision": "first", "reign_end_year": "max", "reign_end_precision": "first",
           "birth_year": "min", "death_year": "max", "sex": "first", "image_url": "first", "wikipedia_url": "first"}
    df = df.sort_values(["wikidata_id", "reign_start_year"]).groupby("wikidata_id", as_index=False).agg(agg)
    df["dynasty_number"] = df["dynasty"].map(dynasty_number)
    # Wikidata carries a few dates for legendary or predynastic figures (e.g. "4001 BC") that no chronology
    # supports; they are nulled here and listed in data/quality_notes.csv so nothing is silently dropped
    notes = []
    for c in ("reign_start_year", "reign_end_year", "birth_year", "death_year"):
        bad = df[c].notna() & ((df[c] < -3400) | (df[c] > 400))
        for _, r in df[bad].iterrows():
            notes.append({"wikidata_id": r["wikidata_id"], "name": r["name"], "field": c, "value_dropped": year_label(r[c]), "reason": "outside 3400 BC - AD 400"})
        df.loc[bad, c] = pd.NA
    pd.DataFrame(notes, columns=["wikidata_id", "name", "field", "value_dropped", "reason"]).to_csv(OUT / "quality_notes.csv", index=False)
    conv = pd.read_csv(ROOT / "data" / "reference" / "dynasties_conventional.csv")
    df = df.merge(conv[["dynasty_number", "period"]], on="dynasty_number", how="left")
    for c in ("reign_start", "reign_end", "birth", "death"):
        df[f"{c}_label"] = df[f"{c}_year"].map(year_label)
    df["reign_length_years"] = (df["reign_end_year"] - df["reign_start_year"]).where(df["reign_start_year"].notna() & df["reign_end_year"].notna())
    cols = ["wikidata_id", "name", "dynasty_number", "dynasty", "period", "reign_start_year", "reign_start_label", "reign_start_precision",
            "reign_end_year", "reign_end_label", "reign_end_precision", "reign_length_years", "birth_year", "birth_label", "death_year",
            "death_label", "sex", "description", "image_url", "wikipedia_url", "dynasty_id"]
    df = df[cols].sort_values(["dynasty_number", "reign_start_year", "name"], na_position="last")
    df.to_csv(OUT / "pharaohs.csv", index=False)
    return df


def build_dynasties():
    rows = json.load(open(RAW / "dynasties.json", encoding="utf-8"))
    recs = [{"dynasty_id": qid(v(r, "dynasty")), "dynasty_wikidata": v(r, "dynastyLabel"), "description": v(r, "dynastyDescription"),
             "wikidata_start_year": astro_year(v(r, "start")), "wikidata_end_year": astro_year(v(r, "end")),
             "period_wikidata": v(r, "periodLabel"), "preceded_by": v(r, "followsLabel"), "wikipedia_url": v(r, "article")} for r in rows]
    df = pd.DataFrame(recs).groupby("dynasty_id", as_index=False).first()
    df["dynasty_number"] = df["dynasty_wikidata"].map(dynasty_number)
    conv = pd.read_csv(ROOT / "data" / "reference" / "dynasties_conventional.csv")
    df = conv.merge(df, on="dynasty_number", how="outer").sort_values(["dynasty_number", "dynasty_wikidata"], na_position="last")
    df["conventional_start_year"] = 1 - df["start_bc"]
    df["conventional_end_year"] = 1 - df["end_bc"]
    df.to_csv(OUT / "dynasties.csv", index=False)
    return df


def build_pyramids():
    rows = json.load(open(RAW / "pyramids.json", encoding="utf-8"))
    recs = []
    for r in rows:
        lat = lon = None
        m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", v(r, "coords") or "")
        if m:
            lon, lat = float(m.group(1)), float(m.group(2))
        recs.append({"wikidata_id": qid(v(r, "pyramid")), "name": v(r, "pyramidLabel"), "description": v(r, "pyramidDescription"),
                     "latitude": lat, "longitude": lon, "height_m": float(v(r, "height")) if v(r, "height") else None,
                     "built_for": v(r, "builtForLabel"), "built_for_id": qid(v(r, "builtFor")), "location": v(r, "locationLabel"),
                     "inception_year": astro_year(v(r, "inception")), "inception_precision": PRECISION.get(int(v(r, "inceptionPrecision") or 0)),
                     "image_url": v(r, "image"), "wikipedia_url": v(r, "article")})
    df = pd.DataFrame(recs)
    df = df[~df["name"].str.match(r"^Q\d+$", na=False)].groupby("wikidata_id", as_index=False).first()
    df["inception_label"] = df["inception_year"].map(year_label)
    df = df.sort_values(["inception_year", "name"], na_position="last")
    df.to_csv(OUT / "pyramids.csv", index=False)
    return df


if __name__ == "__main__":
    p, d, y = build_pharaohs(), build_dynasties(), build_pyramids()
    print(f"pharaohs {len(p)} (with dynasty {p['dynasty'].notna().sum()}, with reign dates {p['reign_start_year'].notna().sum()}, with image {p['image_url'].notna().sum()})")
    print(f"dynasties {len(d)} | pyramids {len(y)} (with coordinates {y['latitude'].notna().sum()}, with height {y['height_m'].notna().sum()})")
    from validate import validate_all
    validate_all()
