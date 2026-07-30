import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


UPSERT_RECORD_SQL = text("""
INSERT INTO bacdive_record (
    bacdive_id,
    dsm_number,
    doi,
    domain_name,
    phylum_name,
    class_name,
    order_name,
    family_name,
    genus_name,
    species_name,
    full_scientific_name,
    strain_designation,
    type_strain,
    ncbi_tax_id,
    ncbi_matching_level,
    description,
    keywords,
    strain_history,
    culture_medium,
    culture_temp,
    culture_ph,
    morphology,
    physiology,
    isolation_info,
    safety_info,
    sequence_info,
    literature_info,
    raw_json,
    source_file
) VALUES (
    :bacdive_id,
    :dsm_number,
    :doi,
    :domain_name,
    :phylum_name,
    :class_name,
    :order_name,
    :family_name,
    :genus_name,
    :species_name,
    :full_scientific_name,
    :strain_designation,
    :type_strain,
    :ncbi_tax_id,
    :ncbi_matching_level,
    :description,
    :keywords,
    :strain_history,
    CAST(:culture_medium AS JSON),
    CAST(:culture_temp AS JSON),
    CAST(:culture_ph AS JSON),
    CAST(:morphology AS JSON),
    CAST(:physiology AS JSON),
    CAST(:isolation_info AS JSON),
    CAST(:safety_info AS JSON),
    CAST(:sequence_info AS JSON),
    CAST(:literature_info AS JSON),
    CAST(:raw_json AS JSON),
    :source_file
)
ON DUPLICATE KEY UPDATE
    dsm_number = VALUES(dsm_number),
    doi = VALUES(doi),
    domain_name = VALUES(domain_name),
    phylum_name = VALUES(phylum_name),
    class_name = VALUES(class_name),
    order_name = VALUES(order_name),
    family_name = VALUES(family_name),
    genus_name = VALUES(genus_name),
    species_name = VALUES(species_name),
    full_scientific_name = VALUES(full_scientific_name),
    strain_designation = VALUES(strain_designation),
    type_strain = VALUES(type_strain),
    ncbi_tax_id = VALUES(ncbi_tax_id),
    ncbi_matching_level = VALUES(ncbi_matching_level),
    description = VALUES(description),
    keywords = VALUES(keywords),
    strain_history = VALUES(strain_history),
    culture_medium = VALUES(culture_medium),
    culture_temp = VALUES(culture_temp),
    culture_ph = VALUES(culture_ph),
    morphology = VALUES(morphology),
    physiology = VALUES(physiology),
    isolation_info = VALUES(isolation_info),
    safety_info = VALUES(safety_info),
    sequence_info = VALUES(sequence_info),
    literature_info = VALUES(literature_info),
    raw_json = VALUES(raw_json),
    source_file = VALUES(source_file),
    updated_at = CURRENT_TIMESTAMP
""")


INSERT_MATCH_SQL = text("""
INSERT IGNORE INTO bacdive_strain_match (
    strain_id,
    bacdive_record_id,
    match_method,
    match_score,
    matched_by
)
SELECT
    s.id,
    br.id,
    'scientific_name',
    1.0,
    br.species_name
FROM strain s
JOIN bacdive_record br
  ON LOWER(TRIM(s.scientific_name)) COLLATE utf8mb4_unicode_ci
   = LOWER(TRIM(br.species_name)) COLLATE utf8mb4_unicode_ci
WHERE s.is_active = 1
""")


PROPAGATE_CHINESE_NAMES_SQL = text("""
UPDATE bacdive_record target
JOIN (
    SELECT species_name, MAX(species_name_zh) AS species_name_zh
    FROM bacdive_record
    WHERE species_name IS NOT NULL
      AND species_name_zh IS NOT NULL
      AND species_name_zh <> ''
    GROUP BY species_name
) translated ON translated.species_name = target.species_name
SET target.species_name_zh = translated.species_name_zh
WHERE target.species_name_zh IS NULL OR target.species_name_zh = ''
""")


COPY_LOCAL_CHINESE_NAMES_SQL = text("""
UPDATE bacdive_record br
JOIN (
    SELECT LOWER(TRIM(scientific_name)) AS scientific_name, MAX(TRIM(name)) AS name
    FROM strain
    WHERE is_active = 1
      AND scientific_name IS NOT NULL
      AND TRIM(scientific_name) <> ''
      AND name IS NOT NULL
      AND TRIM(name) <> ''
    GROUP BY LOWER(TRIM(scientific_name))
) local_name
  ON LOWER(TRIM(br.species_name)) COLLATE utf8mb4_unicode_ci
   = local_name.scientific_name COLLATE utf8mb4_unicode_ci
SET br.species_name_zh = local_name.name,
    br.species_name_zh_source = 'local_strain',
    br.species_name_zh_review_status = 'verified'
WHERE br.species_name_zh IS NULL OR br.species_name_zh = ''
""")


UPDATE_CHINESE_NAME_SQL = text("""
UPDATE bacdive_record
SET species_name_zh = :species_name_zh,
    species_name_zh_source = 'gbif',
    species_name_zh_review_status = 'verified'
WHERE species_name = :species_name
  AND (species_name_zh IS NULL OR species_name_zh = '')
""")


def _contains_chinese(value: Any) -> bool:
    return isinstance(value, str) and any("一" <= char <= "鿿" for char in value)


def fetch_gbif_chinese_name(session: requests.Session, species_name: str) -> str:
    match_response = session.get(
        "https://api.gbif.org/v1/species/match",
        params={"name": species_name, "strict": "true"},
        timeout=12,
    )
    match_response.raise_for_status()
    match = match_response.json()
    if match.get("matchType") != "EXACT" or (match.get("confidence") or 0) < 90:
        return ""

    canonical_name = (match.get("canonicalName") or "").strip()
    if canonical_name and canonical_name.casefold() != species_name.strip().casefold():
        return ""

    taxon_key = match.get("usageKey")
    if not taxon_key:
        return ""

    names_response = session.get(
        f"https://api.gbif.org/v1/species/{taxon_key}/vernacularNames",
        params={"limit": 100},
        timeout=12,
    )
    names_response.raise_for_status()
    candidates = []
    for item in names_response.json().get("results", []):
        chinese_name = (item.get("vernacularName") or "").strip()
        language = (item.get("language") or "").lower()
        if language != "zho" or not _contains_chinese(chinese_name):
            continue
        source = item.get("source") or ""
        candidates.append((source != "Catalogue of Life", chinese_name))

    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1][:255]


def sync_gbif_chinese_names(db, limit: Optional[int] = None, workers: int = 8) -> int:
    with db.engine.begin() as conn:
        conn.execute(PROPAGATE_CHINESE_NAMES_SQL)
        conn.execute(COPY_LOCAL_CHINESE_NAMES_SQL)
        query = """
            SELECT species_name, MIN(bacdive_id) AS first_bacdive_id
            FROM bacdive_record
            WHERE species_name IS NOT NULL
              AND TRIM(species_name) <> ''
              AND species_name_zh IS NULL
            GROUP BY species_name
            ORDER BY first_bacdive_id
        """
        params = {}
        if limit is not None:
            query += " LIMIT :limit"
            params["limit"] = limit
        species_names = [row[0] for row in conn.execute(text(query), params)]

    updates = []
    found = 0
    failed = 0
    processed = 0

    def flush_updates():
        if not updates:
            return
        with db.engine.begin() as conn:
            conn.execute(UPDATE_CHINESE_NAME_SQL, list(updates))
        updates.clear()

    def fetch_one(species_name):
        with requests.Session() as session:
            session.headers["User-Agent"] = "crc-flask-bacdive-import/1.0"
            return fetch_gbif_chinese_name(session, species_name)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(fetch_one, species_name): species_name
            for species_name in species_names
        }
        for future in as_completed(futures):
            species_name = futures[future]
            processed += 1
            try:
                chinese_name = future.result()
            except (requests.RequestException, ValueError) as exc:
                failed += 1
                print(f"GBIF request failed for {species_name!r}: {exc}", file=sys.stderr)
                continue

            if chinese_name:
                found += 1
            updates.append({
                "species_name": species_name,
                "species_name_zh": chinese_name,
            })
            if len(updates) >= 20:
                flush_updates()
            if processed % 20 == 0 or processed == len(species_names):
                print(
                    f"GBIF checked {processed}/{len(species_names)}, "
                    f"found={found}, no_chinese={processed - found - failed}, failed={failed}",
                    flush=True,
                )

    flush_updates()
    print(
        f"GBIF sync finished. checked={len(species_names)}, "
        f"found={found}, failed={failed}"
    )
    return 0


def as_json(value: Any) -> str:
    if value is None:
        value = None
    return json.dumps(value, ensure_ascii=False)


def as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def as_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def shorten(value: Any, max_len: int) -> Optional[str]:
    text_value = as_text(value)
    if text_value is None:
        return None
    return text_value[:max_len]


def extract_ncbi_tax_id(general: Dict[str, Any]) -> Dict[str, Any]:
    value = general.get("NCBI tax id")
    if isinstance(value, dict):
        return {
            "ncbi_tax_id": as_int(value.get("NCBI tax id")),
            "ncbi_matching_level": shorten(value.get("Matching level"), 64),
        }
    return {
        "ncbi_tax_id": as_int(value),
        "ncbi_matching_level": None,
    }


def extract_record(row: Dict[str, Any], source_file: str) -> Optional[Dict[str, Any]]:
    general = row.get("General") or {}
    taxonomy = row.get("Name and taxonomic classification") or {}
    morphology = row.get("Morphology") or {}
    growth = row.get("Culture and growth conditions") or {}
    physiology = row.get("Physiology and metabolism") or {}
    isolation = row.get("Isolation, sampling and environmental information") or {}
    safety = row.get("Interaction and safety") or {}
    sequence = row.get("Sequence information") or {}
    literature = row.get("Literature") or {}

    bacdive_id = as_int(general.get("BacDive-ID"))
    if bacdive_id is None:
        return None

    ncbi = extract_ncbi_tax_id(general)
    strain_history = general.get("strain history")
    if isinstance(strain_history, dict):
        strain_history = strain_history.get("history") or strain_history

    return {
        "bacdive_id": bacdive_id,
        "dsm_number": shorten(general.get("DSM-Number"), 64),
        "doi": shorten(general.get("doi"), 255),
        "domain_name": shorten(taxonomy.get("domain"), 128),
        "phylum_name": shorten(taxonomy.get("phylum"), 128),
        "class_name": shorten(taxonomy.get("class"), 128),
        "order_name": shorten(taxonomy.get("order"), 128),
        "family_name": shorten(taxonomy.get("family"), 128),
        "genus_name": shorten(taxonomy.get("genus"), 128),
        "species_name": shorten(taxonomy.get("species"), 255),
        "full_scientific_name": shorten(taxonomy.get("full scientific name"), 255),
        "strain_designation": shorten(taxonomy.get("strain designation"), 255),
        "type_strain": shorten(taxonomy.get("type strain"), 64),
        "ncbi_tax_id": ncbi["ncbi_tax_id"],
        "ncbi_matching_level": ncbi["ncbi_matching_level"],
        "description": as_text(general.get("description")),
        "keywords": shorten(general.get("keywords"), 255),
        "strain_history": as_text(strain_history),
        "culture_medium": as_json(growth.get("culture medium")),
        "culture_temp": as_json(growth.get("culture temp")),
        "culture_ph": as_json(growth.get("culture pH")),
        "morphology": as_json(morphology),
        "physiology": as_json(physiology),
        "isolation_info": as_json(isolation),
        "safety_info": as_json(safety),
        "sequence_info": as_json(sequence),
        "literature_info": as_json(literature),
        "raw_json": as_json(row),
        "source_file": shorten(source_file, 255),
    }


def iter_records(data_dir: Path, max_files: Optional[int] = None) -> Iterable[Dict[str, Any]]:
    files = sorted(data_dir.glob("bacdive_*.json"))
    if max_files is not None:
        files = files[:max_files]

    for file_path in files:
        with file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        for row in payload.get("records", []):
            extracted = extract_record(row, file_path.name)
            if extracted:
                yield extracted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import downloaded BacDive full JSON batches into MySQL.")
    parser.add_argument("--data-dir", default=str(PROJECT_ROOT / "data" / "bacdive_full"), help="Directory containing bacdive_*.json batch files.")
    parser.add_argument("--batch-size", type=int, default=500, help="Database commit batch size.")
    parser.add_argument("--max-files", type=int, help="Only import the first N batch files. Useful for testing.")
    parser.add_argument("--no-match", action="store_true", help="Do not create bacdive_strain_match rows.")
    parser.add_argument("--sync-gbif-chinese-names", action="store_true", help="Fill standard Chinese names registered by GBIF/Catalogue of Life.")
    parser.add_argument("--gbif-limit", type=int, help="Only check the first N unprocessed unique species names.")
    parser.add_argument("--gbif-workers", type=int, default=8, help="Concurrent GBIF requests (1-8).")
    return parser.parse_args()


def main() -> int:
    from app import create_app
    from app.extensions import db

    args = parse_args()
    if args.gbif_limit is not None and args.gbif_limit < 1:
        print("--gbif-limit must be at least 1", file=sys.stderr)
        return 2
    if not 1 <= args.gbif_workers <= 8:
        print("--gbif-workers must be between 1 and 8", file=sys.stderr)
        return 2

    app = create_app()
    if args.sync_gbif_chinese_names:
        with app.app_context():
            return sync_gbif_chinese_names(db, args.gbif_limit, args.gbif_workers)

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"Data directory does not exist: {data_dir}", file=sys.stderr)
        return 2

    imported = 0
    matched = 0

    with app.app_context():
        pending = []
        for record in iter_records(data_dir, max_files=args.max_files):
            pending.append(record)
            if len(pending) >= args.batch_size:
                imported, matched = flush_batch(pending, imported, matched, db, args.no_match)
                pending = []
                print(f"Imported {imported} records, matched {matched} local strains")

        if pending:
            imported, matched = flush_batch(pending, imported, matched, db, args.no_match)

        with db.engine.begin() as conn:
            conn.execute(PROPAGATE_CHINESE_NAMES_SQL)
            conn.execute(COPY_LOCAL_CHINESE_NAMES_SQL)
            if not args.no_match:
                result = conn.execute(INSERT_MATCH_SQL)
                matched += result.rowcount or 0

    print(f"Finished. imported_or_updated={imported}, matched={matched}, data_dir={data_dir}")
    return 0


def flush_batch(records, imported: int, matched: int, db, no_match: bool):
    with db.engine.begin() as conn:
        conn.execute(UPSERT_RECORD_SQL, records)
        imported += len(records)
    return imported, matched


if __name__ == "__main__":
    if os.name == "nt":
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")
    raise SystemExit(main())
