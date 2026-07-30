import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def import_bacdive_module():
    try:
        import bacdive  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "bacdive package is not available in the current interpreter."
        ) from exc
    return bacdive


def resolve_client_class(bacdive_module):
    client_cls = getattr(bacdive_module, "BacdiveClient", None)
    if client_cls is None:
        raise RuntimeError("Could not find BacdiveClient in bacdive package.")
    return client_cls


def fetch_batch(client, ids: List[int]) -> List[Dict[str, Any]]:
    client.search(id=ids)
    rows = list(client.retrieve())
    return [row for row in rows if isinstance(row, dict)]


def save_batch(out_dir: Path, start_id: int, end_id: int, rows: List[Dict[str, Any]]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"bacdive_{start_id}_{end_id}.json"
    payload = {
        "start_id": start_id,
        "end_id": end_id,
        "record_count": len(rows),
        "records": rows,
    }
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return target


def save_manifest(manifest_path: Path, payload: Dict[str, Any]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Brute-force BacDive public records by ID range.")
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "data" / "bacdive_full"), help="Directory for downloaded JSON batches.")
    parser.add_argument("--start-id", type=int, default=1, help="Starting BacDive ID.")
    parser.add_argument("--end-id", type=int, default=50000, help="Ending BacDive ID.")
    parser.add_argument("--batch-size", type=int, default=100, help="How many IDs to request per batch.")
    parser.add_argument("--stop-empty-batches", type=int, default=100, help="Stop after this many consecutive empty batches.")
    parser.add_argument("--manifest", default=str(PROJECT_ROOT / "data" / "bacdive_full" / "manifest.json"), help="Progress manifest file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.start_id < 1 or args.end_id < args.start_id or args.batch_size < 1:
        print("Invalid range or batch size.", file=sys.stderr)
        return 2

    bacdive_module = import_bacdive_module()
    client_cls = resolve_client_class(bacdive_module)
    client = client_cls(public=True)

    out_dir = Path(args.out_dir)
    manifest_path = Path(args.manifest)

    total_records = 0
    saved_batches = 0
    empty_batches = 0

    for batch_start in range(args.start_id, args.end_id + 1, args.batch_size):
        batch_end = min(batch_start + args.batch_size - 1, args.end_id)
        ids = list(range(batch_start, batch_end + 1))
        print(f"Fetching ID range {batch_start}-{batch_end}")

        try:
            rows = fetch_batch(client, ids)
        except Exception as exc:
            print(f"  failed: {exc}", file=sys.stderr)
            save_manifest(manifest_path, {
                "last_start_id": batch_start,
                "last_end_id": batch_end,
                "total_records": total_records,
                "saved_batches": saved_batches,
                "empty_batches": empty_batches,
                "status": "failed",
                "error": str(exc),
            })
            return 1

        if rows:
            target = save_batch(out_dir, batch_start, batch_end, rows)
            batch_ids = [row.get("General", {}).get("BacDive-ID") for row in rows]
            print(f"  saved {len(rows)} record(s) -> {target} | ids {min(batch_ids)}..{max(batch_ids)}")
            total_records += len(rows)
            saved_batches += 1
            empty_batches = 0
        else:
            print("  empty batch")
            empty_batches += 1

        save_manifest(manifest_path, {
            "last_start_id": batch_start,
            "last_end_id": batch_end,
            "total_records": total_records,
            "saved_batches": saved_batches,
            "empty_batches": empty_batches,
            "status": "running",
        })

        if empty_batches >= args.stop_empty_batches:
            print(f"Stopping after {empty_batches} consecutive empty batches.")
            break

    save_manifest(manifest_path, {
        "last_start_id": batch_start,
        "last_end_id": batch_end,
        "total_records": total_records,
        "saved_batches": saved_batches,
        "empty_batches": empty_batches,
        "status": "completed",
    })
    print(f"Finished. saved_batches={saved_batches}, total_records={total_records}, output={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
