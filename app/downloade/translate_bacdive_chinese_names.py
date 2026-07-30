import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SELECT_MISSING_SQL = text("""
SELECT species_name, MIN(bacdive_id) AS first_bacdive_id
FROM bacdive_record
WHERE species_name IS NOT NULL
  AND LENGTH(TRIM(species_name)) > 0
  AND COALESCE(LENGTH(TRIM(species_name_zh)), 0) = 0
GROUP BY species_name
ORDER BY first_bacdive_id, species_name
""")

UPDATE_NAME_SQL = text("""
UPDATE bacdive_record
SET species_name_zh = :chinese_name,
    species_name_zh_source = 'deepseek_api',
    species_name_zh_review_status = 'pending'
WHERE species_name = :species_name
  AND COALESCE(LENGTH(TRIM(species_name_zh)), 0) = 0
""")

SYSTEM_PROMPT = """你是细菌分类学中文命名助手。只返回JSON对象，键必须为原学名，值为纯中文菌名。"""

CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")
VALID_SUFFIXES = (
    "菌", "杆菌", "球菌", "弧菌", "螺菌", "放线菌", "古菌",
    "芽胞杆菌", "芽孢杆菌", "单胞菌", "拟杆菌", "链霉菌",
)
FORBIDDEN_TERMS = ("病毒", "真菌", "未命名", "未知", "不确定")


def parse_args():
    parser = argparse.ArgumentParser(description="Fill missing BacDive Chinese species names with DeepSeek API.")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--api-url", default="https://api.deepseek.com/chat/completions")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--checkpoint", default=str(PROJECT_ROOT / "data" / "bacdive_chinese_translation.jsonl"))
    return parser.parse_args()


def valid_translation(value):
    if not isinstance(value, str):
        return False
    value = value.strip()
    return (
        2 <= len(value) <= 40
        and CHINESE_RE.search(value) is not None
        and LATIN_RE.search(value) is None
        and not any(term in value for term in FORBIDDEN_TERMS)
        and value.endswith(VALID_SUFFIXES)
    )


def extract_json(raw):
    raw = (raw or "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(raw[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model response is not a JSON object")
    return parsed


def get_api_key():
    key = os.getenv("DEEPSEEK_API_KEY")
    if key or os.name != "nt":
        return key
    try:
        import winreg

        path = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as handle:
            return winreg.QueryValueEx(handle, "DEEPSEEK_API_KEY")[0]
    except (FileNotFoundError, OSError):
        return None


def translate_batch(session, args, names, api_key):
    response = session.post(
        args.api_url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": args.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "请翻译以下学名：" + ", ".join(names)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": max(160, len(names) * 50),
        },
        timeout=args.timeout,
    )
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("DeepSeek API returned no choices")
    content = (choices[0].get("message") or {}).get("content")
    return extract_json(content), payload


def translate_with_retries(session, args, names, api_key):
    pending = list(names)
    accepted = {}
    errors = {}
    for attempt in range(1, args.retries + 2):
        if not pending:
            break
        try:
            translated, _ = translate_batch(session, args, pending, api_key)
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            print(
                f"Attempt {attempt} failed for {len(pending)} names: {exc}",
                flush=True,
            )
            errors.update({name: str(exc) for name in pending})
            if attempt <= args.retries:
                time.sleep(min(attempt * 2, 10))
            continue

        next_pending = []
        for name in pending:
            chinese_name = str(translated.get(name) or "").strip()
            if valid_translation(chinese_name):
                accepted[name] = chinese_name
                errors.pop(name, None)
            else:
                errors[name] = f"invalid translation: {chinese_name!r}"
                next_pending.append(name)
        pending = next_pending
    return accepted, errors


def is_complex_name(name):
    tokens = name.split()
    return len(tokens) > 3 or any(
        marker in tokens for marker in ("subsp.", "ssp.", "var.", "pv.", "f.")
    )


def append_checkpoint(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    from app import create_app
    from app.extensions import db

    args = parse_args()
    if args.batch_size < 1 or args.batch_size > 100:
        raise SystemExit("--batch-size must be between 1 and 100")
    checkpoint_path = Path(args.checkpoint)
    api_key = get_api_key()
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is not available")
    app = create_app()

    with app.app_context():
        with db.engine.begin() as conn:
            names = [row[0] for row in conn.execute(SELECT_MISSING_SQL)]
        if args.limit is not None:
            names = names[:args.limit]

        simple_names = [name for name in names if not is_complex_name(name)]
        complex_names = [name for name in names if is_complex_name(name)]
        batches = [
            simple_names[start:start + args.batch_size]
            for start in range(0, len(simple_names), args.batch_size)
        ]
        batches.extend([[name] for name in complex_names])

        total = len(names)
        print(
            f"Starting BacDive Chinese-name translation: total={total}, "
            f"simple={len(simple_names)}, complex={len(complex_names)}, model={args.model}",
            flush=True,
        )
        session = requests.Session()
        completed = 0
        failed = 0
        processed = 0

        for batch in batches:
            accepted, errors = translate_with_retries(session, args, batch, api_key)
            if accepted:
                params = [
                    {"species_name": name, "chinese_name": translated}
                    for name, translated in accepted.items()
                ]
                with db.engine.begin() as conn:
                    conn.execute(UPDATE_NAME_SQL, params)

            now = datetime.now(timezone.utc).isoformat()
            audit_rows = [
                {
                    "timestamp": now,
                    "species_name": name,
                    "chinese_name": accepted.get(name),
                    "status": "written" if name in accepted else "rejected",
                    "error": errors.get(name),
                    "model": args.model,
                }
                for name in batch
            ]
            append_checkpoint(checkpoint_path, audit_rows)
            completed += len(accepted)
            failed += len(batch) - len(accepted)
            processed += len(batch)
            print(
                f"Processed {processed}/{total}; "
                f"written={completed}, rejected={failed}",
                flush=True,
            )

    print(f"Translation finished: total={total}, written={completed}, rejected={failed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
