"""Step 3: validate the published tables with pandera. Fails loudly on anything that would embarrass the dataset:
duplicate ids, reigns that end before they start, years outside 3300 BC – AD 400, coordinates outside Egypt,
heights that are not positive, broken URLs. Writes data/validation_report.json."""
import json
from pathlib import Path

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
YEAR = Check.in_range(-3300, 400, error="year outside 3300 BC - AD 400")
URL = Check.str_startswith("http", error="not a URL")

pharaohs = DataFrameSchema({
    "wikidata_id": Column(str, Check.str_matches(r"^Q\d+$"), unique=True),
    "name": Column(str, Check.str_length(min_value=1)),
    "dynasty_number": Column(float, Check.in_range(0, 33), nullable=True),
    "period": Column(str, nullable=True),
    "reign_start_year": Column(float, YEAR, nullable=True),
    "reign_end_year": Column(float, YEAR, nullable=True),
    "reign_length_years": Column(float, Check.in_range(0, 100, error="reign longer than a century"), nullable=True),
    "birth_year": Column(float, YEAR, nullable=True),
    "death_year": Column(float, YEAR, nullable=True),
    "sex": Column(str, Check.isin(["male", "female"]), nullable=True),
    "image_url": Column(str, URL, nullable=True),
    "wikipedia_url": Column(str, URL, nullable=True),
}, checks=[Check(lambda df: (df["reign_end_year"].isna() | df["reign_start_year"].isna() | (df["reign_end_year"] >= df["reign_start_year"])).all(),
                 error="a reign ends before it starts")], strict=False, coerce=True)

dynasties = DataFrameSchema({
    "dynasty_number": Column(float, Check.in_range(0, 33), nullable=True),
    "start_bc": Column(float, Check.in_range(0, 3300), nullable=True),
    "end_bc": Column(float, Check.in_range(0, 3300), nullable=True),
    "wikidata_start_year": Column(float, YEAR, nullable=True),
    "wikidata_end_year": Column(float, YEAR, nullable=True),
}, checks=[Check(lambda df: (df["start_bc"].isna() | df["end_bc"].isna() | (df["start_bc"] >= df["end_bc"])).all(), error="a BC dynasty ends before it starts")],
   strict=False, coerce=True)

pyramids = DataFrameSchema({
    "wikidata_id": Column(str, Check.str_matches(r"^Q\d+$"), unique=True),
    "name": Column(str),
    "latitude": Column(float, Check.in_range(21.5, 32.0, error="latitude outside Egypt"), nullable=True),
    "longitude": Column(float, Check.in_range(24.5, 37.0, error="longitude outside Egypt"), nullable=True),
    "height_m": Column(float, Check.in_range(0.1, 150, error="height outside 0.1-150 m"), nullable=True),
    "inception_year": Column(float, YEAR, nullable=True),
}, strict=False, coerce=True)


def validate_all():
    report = {}
    for name, schema in [("pharaohs", pharaohs), ("dynasties", dynasties), ("pyramids", pyramids)]:
        df = pd.read_csv(DATA / f"{name}.csv")
        try:
            schema.validate(df, lazy=True)
            report[name] = {"rows": len(df), "status": "passed"}
        except pa.errors.SchemaErrors as e:
            fails = e.failure_cases
            report[name] = {"rows": len(df), "status": "FAILED", "failures": fails[["column", "check", "failure_case"]].astype(str).head(20).to_dict("records")}
        print(name, report[name]["status"], f"({len(df)} rows)")
    json.dump(report, open(DATA / "validation_report.json", "w"), indent=1)
    if any(r["status"] != "passed" for r in report.values()):
        raise SystemExit("validation failed - see data/validation_report.json")


if __name__ == "__main__":
    validate_all()
