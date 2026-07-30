import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def slugify(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unknown"


def load_query_names(query_file: Path) -> List[str]:
    names: List[str] = []
    with query_file.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            name = raw_line.strip()
            if not name or name.startswith("#"):
                continue
            names.append(name)
    return names


def normalize_taxonomy_query(query: str) -> Dict[str, Any]:
    raw = (query or "").strip()
    collapsed = re.sub(r"\s+", " ", raw)
    parts = collapsed.split(" ")

    genus = parts[0] if parts else ""
    species = parts[1] if len(parts) > 1 else None
    remainder = parts[2:] if len(parts) > 2 else []

    lowered = collapsed.lower()
    non_standard_markers = (
        " complex",
        " group",
        " cluster",
        " clade",
        " uncultured",
        " bacterium",
        " archaeon",
        " fungus",
        " cf.",
        " aff.",
        " sp.",
        " spp.",
    )

    is_standard_binomial = bool(genus and species and len(parts) == 2 and not any(marker in lowered for marker in non_standard_markers))
    return {
        "raw": raw,
        "normalized": collapsed,
        "genus": genus,
        "species": species,
        "remainder": remainder,
        "is_standard_binomial": is_standard_binomial,
        "has_non_standard_marker": any(marker in lowered for marker in non_standard_markers),
    }


def export_queries_from_db(output_file: Path) -> int:
    from app import create_app
    from app.models.strain import Strain

    app = create_app()
    seen = set()
    rows: List[str] = []

    with app.app_context():
        for strain in Strain.query.order_by(Strain.scientific_name.asc(), Strain.name.asc()).all():
            query_name = (strain.scientific_name or strain.name or "").strip()
            if not query_name or query_name in seen:
                continue
            seen.add(query_name)
            rows.append(query_name)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(f"{row}\n")
    return len(rows)


def import_bacdive_module():
    try:
        import bacdive  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "bacdive package is not available in the current interpreter. "
            "Install it in the same environment that runs this script."
        ) from exc
    return bacdive


def resolve_client_class(bacdive_module):
    for attr_name in ("BacdiveClient", "BacDiveClient", "Client"):
        client_cls = getattr(bacdive_module, attr_name, None)
        if client_cls is not None:
            return client_cls
    raise RuntimeError("Could not find a BacDive client class in the installed bacdive package.")


def instantiate_client(client_cls, username: Optional[str], password: Optional[str]):
    attempts: List[Tuple[Tuple[Any, ...], Dict[str, Any]]] = []
    if username and password:
        attempts.extend([
            ((username, password), {"public": False}),
            ((), {"user": username, "password": password, "public": False}),
        ])
    attempts.append(((), {"public": True}))
    attempts.append(((), {}))

    last_error = None
    for args, kwargs in attempts:
        try:
            return client_cls(*args, **kwargs)
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Could not initialize BacDive client: {last_error}")


def _call_search(client, query: str) -> Any:
    search_method = getattr(client, "search", None)
    if callable(search_method):
        variants = [
            {"taxonomy": query},
            {"species": query},
            {"name": query},
            {"query": query},
        ]
        for kwargs in variants:
            try:
                return search_method(**kwargs)
            except TypeError:
                continue
        try:
            return search_method(query)
        except TypeError:
            pass

    for method_name in (
        "search_by_taxonomy",
        "search_taxonomy",
        "find_by_taxonomy",
        "find",
    ):
        method = getattr(client, method_name, None)
        if callable(method):
            return method(query)

    raise RuntimeError("Installed bacdive client does not expose a usable search method.")


def _call_taxonomy_ids(client, genus: str, species: Optional[str]) -> Any:
    get_ids = getattr(client, "getIDsByTaxonomy", None)
    if not callable(get_ids):
        raise RuntimeError("Installed bacdive client does not expose getIDsByTaxonomy.")
    if species:
        return get_ids(genus, species)
    return get_ids(genus)


def _search_by_ids(client, ids: List[Any]) -> Any:
    if not ids:
        return {"count": 0, "results": []}
    search_method = getattr(client, "search", None)
    if not callable(search_method):
        raise RuntimeError("Installed bacdive client does not expose a usable search method.")
    return search_method(id=ids)


def _collect_records(client, search_result: Any, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if isinstance(search_result, dict):
        # BacDive search helpers may return pagination metadata or ID lists.
        # Those are not the final strain records and must be resolved via retrieve().
        if search_result.get("count") == 0 and search_result.get("results") == []:
            return []
        if "results" in search_result or "count" in search_result:
            search_result = None

    if isinstance(search_result, list):
        return [item for item in search_result if isinstance(item, dict)]
    if isinstance(search_result, dict):
        return [search_result]

    for method_name in ("retrieve", "retrieve_all", "results", "get_results"):
        method = getattr(client, method_name, None)
        if callable(method):
            try:
                result = method()
            except TypeError:
                continue

            if isinstance(result, dict):
                return [result]
            if isinstance(result, list):
                return [item for item in result if isinstance(item, dict)]
            if isinstance(result, Iterable):
                rows = []
                for item in result:
                    if isinstance(item, dict):
                        rows.append(item)
                        if limit and len(rows) >= limit:
                            break
                return rows

    if isinstance(search_result, Iterable) and not isinstance(search_result, (str, bytes)):
        rows = []
        for item in search_result:
            if isinstance(item, dict):
                rows.append(item)
                if limit and len(rows) >= limit:
                    break
        if rows:
            return rows

    return []


def query_bacdive(client, query: str, limit: Optional[int] = None) -> Dict[str, Any]:
    query_meta = normalize_taxonomy_query(query)
    strategy = "taxonomy_string"
    note = ""

    if query_meta["is_standard_binomial"]:
        strategy = "getIDsByTaxonomy"
        id_result = _call_taxonomy_ids(client, query_meta["genus"], query_meta["species"])
        ids = list((id_result or {}).get("results", []))
        if limit:
            ids = ids[:limit]
        search_result = _search_by_ids(client, ids)
    else:
        search_result = _call_search(client, query_meta["normalized"])
        if query_meta["has_non_standard_marker"] or query_meta["remainder"]:
            note = "Query is not a strict genus+species binomial. Zero results may be expected in BacDive taxonomy search."

    records = _collect_records(client, search_result, limit=limit)
    return {
        "query": query,
        "normalized_query": query_meta["normalized"],
        "genus": query_meta["genus"],
        "species": query_meta["species"],
        "is_standard_binomial": query_meta["is_standard_binomial"],
        "search_strategy": strategy,
        "note": note,
        "record_count": len(records),
        "records": records,
    }


def save_result(out_dir: Path, payload: Dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{slugify(payload['query'])}.json"
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download BacDive search results into local JSON files.")
    parser.add_argument("--query-file", help="Text file containing one species name per line.")
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "data" / "bacdive"), help="Output directory for JSON files.")
    parser.add_argument("--username", default=os.getenv("BACDIVE_USERNAME"), help="Optional BacDive username.")
    parser.add_argument("--password", default=os.getenv("BACDIVE_PASSWORD"), help="Optional BacDive password.")
    parser.add_argument("--export-strain-queries", help="Export unique scientific names from the local strain table into a text file.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of records to save per query.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.export_strain_queries:
        output_file = Path(args.export_strain_queries)
        count = export_queries_from_db(output_file)
        print(f"Exported {count} strain names to {output_file}")
        return 0

    if not args.query_file:
        print("--query-file is required unless you use --export-strain-queries", file=sys.stderr)
        return 2

    query_file = Path(args.query_file)
    if not query_file.exists():
        print(f"Query file not found: {query_file}", file=sys.stderr)
        return 2

    queries = load_query_names(query_file)
    if not queries:
        print("No valid query names found in the input file.", file=sys.stderr)
        return 2

    bacdive_module = import_bacdive_module()
    client_cls = resolve_client_class(bacdive_module)
    client = instantiate_client(client_cls, args.username, args.password)

    out_dir = Path(args.out_dir)
    success = 0
    failed = 0

    for idx, query in enumerate(queries, start=1):
        print(f"[{idx}/{len(queries)}] Querying BacDive: {query}")
        try:
            payload = query_bacdive(client, query, limit=args.limit)
            target = save_result(out_dir, payload)
            if payload["record_count"] == 0 and payload.get("note"):
                print(f"  no records: {payload['note']}")
            print(f"  saved {payload['record_count']} record(s) -> {target}")
            success += 1
        except Exception as exc:
            print(f"  failed: {exc}", file=sys.stderr)
            failed += 1

    print(f"Finished. success={success}, failed={failed}, output={out_dir}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
