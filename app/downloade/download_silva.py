import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def infer_filename(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    return name or "silva_download.dat"


def download_file(url: str, target: Path, chunk_size: int = 1024 * 1024) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    existing_size = target.stat().st_size if target.exists() else 0
    headers = {"Range": f"bytes={existing_size}-"} if existing_size else {}

    with requests.get(url, headers=headers, stream=True, timeout=120) as response:
        response.raise_for_status()
        resumed = existing_size > 0 and response.status_code == 206
        if existing_size and not resumed:
            existing_size = 0
        response_size = int(response.headers.get("content-length", "0") or 0)
        total = existing_size + response_size if response_size else 0
        written = existing_size

        with target.open("ab" if resumed else "wb") as handle:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
                if total > 0:
                    percent = written * 100.0 / total
                    print(f"  {written}/{total} bytes ({percent:.1f}%)", end="\r", flush=True)
                else:
                    print(f"  {written} bytes", end="\r", flush=True)

    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a SILVA release file from a direct URL.")
    parser.add_argument("--url", required=True, help="Direct download URL from the SILVA archive/current release page.")
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "data" / "silva"), help="Directory where the file will be saved.")
    parser.add_argument("--filename", help="Optional output filename. Defaults to the filename inferred from the URL.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    filename = args.filename or infer_filename(args.url)
    target = out_dir / filename

    print(f"Downloading SILVA file to {target}")
    try:
        download_file(args.url, target)
    except requests.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    size = target.stat().st_size if target.exists() else 0
    print(f"Saved {size} bytes to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
