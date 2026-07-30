import argparse
import gzip
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, TextIO

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


UPSERT_SQL = text("""
INSERT INTO silva_ssu_sequence (
    sequence_identifier, accession, organism_name, taxonomy, domain_name, phylum_name,
    class_name, order_name, family_name, genus_name, species_name,
    sequence, sequence_length, silva_release, source_file
) VALUES (
    :sequence_identifier, :accession, :organism_name, :taxonomy, :domain_name, :phylum_name,
    :class_name, :order_name, :family_name, :genus_name, :species_name,
    :sequence, :sequence_length, :silva_release, :source_file
)
ON DUPLICATE KEY UPDATE
    accession = VALUES(accession), organism_name = VALUES(organism_name), taxonomy = VALUES(taxonomy),
    domain_name = VALUES(domain_name), phylum_name = VALUES(phylum_name),
    class_name = VALUES(class_name), order_name = VALUES(order_name),
    family_name = VALUES(family_name), genus_name = VALUES(genus_name),
    species_name = VALUES(species_name), sequence = VALUES(sequence),
    sequence_length = VALUES(sequence_length), silva_release = VALUES(silva_release),
    source_file = VALUES(source_file), updated_at = CURRENT_TIMESTAMP
""")


def open_fasta(path: Path) -> TextIO:
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def parse_header(header: str, sequence: str, release: str, source_file: str) -> Optional[Dict[str, object]]:
    identifier, separator, taxonomy = header.partition(" ")
    sequence_identifier = identifier.strip()
    accession = sequence_identifier.split(".", 1)[0]
    taxonomy = taxonomy.strip().strip(";") if separator else ""
    if not sequence_identifier or not taxonomy or not sequence:
        return None

    taxa = [part.strip() for part in taxonomy.split(";") if part.strip()]
    organism = taxa[-1] if taxa else None
    species = organism if organism and " " in organism else None
    genus = taxa[-2] if len(taxa) > 1 else None

    return {
        "sequence_identifier": sequence_identifier[:191],
        "accession": accession[:128],
        "organism_name": organism[:512] if organism else None,
        "taxonomy": taxonomy,
        "domain_name": taxa[0][:128] if taxa else None,
        "phylum_name": None,
        "class_name": None,
        "order_name": None,
        "family_name": None,
        "genus_name": genus[:128] if genus else None,
        "species_name": species[:255] if species else None,
        "sequence": sequence,
        "sequence_length": len(sequence),
        "silva_release": release,
        "source_file": source_file[:255],
    }


def iter_fasta(path: Path, release: str) -> Iterable[Optional[Dict[str, object]]]:
    header = None
    chunks = []
    with open_fasta(path) as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    record = parse_header(header, "".join(chunks).upper(), release, path.name)
                    yield record
                header = line[1:]
                chunks = []
            elif header is not None:
                chunks.append(line.replace("-", "").replace(".", ""))
        if header is not None:
            record = parse_header(header, "".join(chunks).upper(), release, path.name)
            yield record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a SILVA taxonomy FASTA into crc_ai.")
    parser.add_argument("fasta", type=Path, help="SILVA .fasta or .fasta.gz file")
    parser.add_argument("--release", help="SILVA release; inferred from filename when omitted")
    parser.add_argument("--batch-size", type=int, default=1000)
    return parser.parse_args()


def main() -> int:
    from app import create_app
    from app.extensions import db
    from app.models.silva import SilvaSsuSequence

    args = parse_args()
    if not args.fasta.is_file():
        print(f"FASTA file does not exist: {args.fasta}", file=sys.stderr)
        return 2
    release_match = re.search(r"SILVA_([0-9.]+)_", args.fasta.name)
    release = args.release or (release_match.group(1) if release_match else "unknown")
    app = create_app()
    imported = 0
    skipped = 0
    batch = []

    with app.app_context():
        SilvaSsuSequence.__table__.create(bind=db.engine, checkfirst=True)
        for record in iter_fasta(args.fasta, release):
            if record is None:
                skipped += 1
                continue
            batch.append(record)
            if len(batch) >= args.batch_size:
                db.session.execute(UPSERT_SQL, batch)
                db.session.commit()
                imported += len(batch)
                batch.clear()
                print(f"Imported {imported:,} records", end="\r", flush=True)
        if batch:
            db.session.execute(UPSERT_SQL, batch)
            db.session.commit()
            imported += len(batch)

    print(f"\nFinished: {imported:,} records imported/upserted, {skipped:,} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
