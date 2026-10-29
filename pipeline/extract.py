"""Step 1: pull the raw records from Wikidata's SPARQL endpoint.

Three queries, run one minute apart (the endpoint rate-limits anonymous clients):
  pharaohs   - everyone who held the position "pharaoh" (Q37110) or has it as occupation, with the reign
               start/end recorded on that position statement (and its precision), dynasty, birth, death,
               sex, image and English Wikipedia article;
  dynasties  - every dynasty referenced by those pharaohs, with its dates, period and predecessor;
  pyramids   - every Egyptian pyramid with coordinates, the pharaoh it was built for, height and location.

Writes data/raw/<name>.json (the SPARQL JSON as returned) and data/raw/manifest.json with the query text
and the retrieval time, so every published row can be traced back to its source query.
"""
import json, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "pharaohs-of-egypt/0.1 (https://github.com/engomaressam/pharaohs-of-egypt)", "Accept": "application/sparql-results+json"}
LABEL = 'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }'

QUERIES = {
    "pharaohs": f"""
SELECT DISTINCT ?pharaoh ?pharaohLabel ?pharaohDescription ?start ?startPrecision ?end ?endPrecision ?dynasty ?dynastyLabel
                ?birth ?death ?sex ?sexLabel ?image ?article WHERE {{
  {{ ?pharaoh wdt:P39 wd:Q37110 }} UNION {{ ?pharaoh wdt:P106 wd:Q37110 }}
  OPTIONAL {{ ?pharaoh p:P39 ?st . ?st ps:P39 wd:Q37110 .
             OPTIONAL {{ ?st pqv:P580 ?sv . ?sv wikibase:timeValue ?start ; wikibase:timePrecision ?startPrecision }}
             OPTIONAL {{ ?st pqv:P582 ?ev . ?ev wikibase:timeValue ?end ; wikibase:timePrecision ?endPrecision }} }}
  OPTIONAL {{ ?pharaoh wdt:P53 ?dynasty }}
  OPTIONAL {{ ?pharaoh wdt:P569 ?birth }} OPTIONAL {{ ?pharaoh wdt:P570 ?death }} OPTIONAL {{ ?pharaoh wdt:P21 ?sex }}
  OPTIONAL {{ ?pharaoh wdt:P18 ?image }}
  OPTIONAL {{ ?article schema:about ?pharaoh ; schema:isPartOf <https://en.wikipedia.org/> }}
  {LABEL}
}} LIMIT 20000""",
    "dynasties": f"""
SELECT DISTINCT ?dynasty ?dynastyLabel ?dynastyDescription ?start ?startPrecision ?end ?endPrecision ?period ?periodLabel
                ?follows ?followsLabel ?article WHERE {{
  {{ SELECT DISTINCT ?dynasty WHERE {{ {{ ?p wdt:P39 wd:Q37110 }} UNION {{ ?p wdt:P106 wd:Q37110 }} ?p wdt:P53 ?dynasty }} }}
  OPTIONAL {{ ?dynasty p:P580/psv:P580 ?sv . ?sv wikibase:timeValue ?start ; wikibase:timePrecision ?startPrecision }}
  OPTIONAL {{ ?dynasty p:P582/psv:P582 ?ev . ?ev wikibase:timeValue ?end ; wikibase:timePrecision ?endPrecision }}
  OPTIONAL {{ ?dynasty wdt:P361 ?period }} OPTIONAL {{ ?dynasty wdt:P155 ?follows }}
  OPTIONAL {{ ?article schema:about ?dynasty ; schema:isPartOf <https://en.wikipedia.org/> }}
  {LABEL}
}}""",
    "pyramids": f"""
SELECT DISTINCT ?pyramid ?pyramidLabel ?pyramidDescription ?coords ?height ?builtFor ?builtForLabel ?location ?locationLabel
                ?inception ?inceptionPrecision ?image ?article WHERE {{
  ?pyramid wdt:P31/wdt:P279* wd:Q12516 ; wdt:P17 wd:Q79 .
  OPTIONAL {{ ?pyramid wdt:P625 ?coords }} OPTIONAL {{ ?pyramid wdt:P2048 ?height }}
  OPTIONAL {{ ?pyramid wdt:P88 ?builtFor }} OPTIONAL {{ ?pyramid wdt:P131 ?location }}
  OPTIONAL {{ ?pyramid p:P571/psv:P571 ?iv . ?iv wikibase:timeValue ?inception ; wikibase:timePrecision ?inceptionPrecision }}
  OPTIONAL {{ ?pyramid wdt:P18 ?image }}
  OPTIONAL {{ ?article schema:about ?pyramid ; schema:isPartOf <https://en.wikipedia.org/> }}
  {LABEL}
}} LIMIT 5000""",
}


def run(name, query):
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(query)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                rows = json.load(r)["results"]["bindings"]
            json.dump(rows, open(RAW / f"{name}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
            return rows
        except urllib.error.HTTPError as e:
            wait = 70 if e.code == 429 else 20
            print(f"  {name}: HTTP {e.code}, retrying in {wait}s", flush=True)
            time.sleep(wait)
    raise SystemExit(f"{name}: gave up")


if __name__ == "__main__":
    manifest = {"retrieved": datetime.now(timezone.utc).isoformat(timespec="seconds"), "endpoint": "https://query.wikidata.org/sparql", "queries": QUERIES, "rows": {}}
    for i, (name, query) in enumerate(QUERIES.items()):
        if i:
            time.sleep(65)                        # one request a minute keeps the endpoint happy
        rows = run(name, query)
        manifest["rows"][name] = len(rows)
        print(f"{name}: {len(rows)} rows", flush=True)
    json.dump(manifest, open(RAW / "manifest.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("done", manifest["rows"])
