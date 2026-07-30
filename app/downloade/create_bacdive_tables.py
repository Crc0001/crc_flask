import os
import sys
from pathlib import Path

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


CREATE_BACDIVE_RECORD_SQL = """
CREATE TABLE IF NOT EXISTS bacdive_record (
    id INT AUTO_INCREMENT PRIMARY KEY,
    bacdive_id INT NOT NULL UNIQUE,
    dsm_number VARCHAR(64),
    doi VARCHAR(255),

    domain_name VARCHAR(128),
    phylum_name VARCHAR(128),
    class_name VARCHAR(128),
    order_name VARCHAR(128),
    family_name VARCHAR(128),
    genus_name VARCHAR(128),
    species_name VARCHAR(255),
    species_name_zh VARCHAR(255),
    species_name_zh_source VARCHAR(64),
    species_name_zh_review_status VARCHAR(32),
    full_scientific_name VARCHAR(255),
    strain_designation VARCHAR(255),
    type_strain VARCHAR(64),

    ncbi_tax_id INT,
    ncbi_matching_level VARCHAR(64),

    description TEXT,
    keywords VARCHAR(255),
    strain_history TEXT,

    culture_medium JSON,
    culture_temp JSON,
    culture_ph JSON,

    morphology JSON,
    physiology JSON,
    isolation_info JSON,
    safety_info JSON,
    sequence_info JSON,
    literature_info JSON,

    raw_json JSON NOT NULL,

    source_file VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_bacdive_taxid (ncbi_tax_id),
    INDEX idx_bacdive_genus_species (genus_name, species_name),
    INDEX idx_bacdive_species_name (species_name),
    INDEX idx_bacdive_species_name_zh (species_name_zh),
    INDEX idx_bacdive_zh_review_status (species_name_zh_review_status),
    INDEX idx_bacdive_full_name (full_scientific_name(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


CREATE_BACDIVE_STRAIN_MATCH_SQL = """
CREATE TABLE IF NOT EXISTS bacdive_strain_match (
    id INT AUTO_INCREMENT PRIMARY KEY,
    strain_id INT NOT NULL,
    bacdive_record_id INT NOT NULL,

    match_method VARCHAR(64),
    match_score FLOAT,
    matched_by VARCHAR(255),

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_strain_bacdive (strain_id, bacdive_record_id),
    INDEX idx_match_strain (strain_id),
    INDEX idx_match_bacdive (bacdive_record_id),

    CONSTRAINT fk_bacdive_match_strain
        FOREIGN KEY (strain_id) REFERENCES strain(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_bacdive_match_record
        FOREIGN KEY (bacdive_record_id) REFERENCES bacdive_record(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def main() -> int:
    from app import create_app
    from app.extensions import db

    app = create_app()
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text(CREATE_BACDIVE_RECORD_SQL))
            conn.execute(text(CREATE_BACDIVE_STRAIN_MATCH_SQL))
            column_exists = conn.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'bacdive_record'
                  AND COLUMN_NAME = 'species_name_zh'
            """)).scalar()
            if not column_exists:
                conn.execute(text("""
                    ALTER TABLE bacdive_record
                    ADD COLUMN species_name_zh VARCHAR(255) NULL AFTER species_name,
                    ADD INDEX idx_bacdive_species_name_zh (species_name_zh)
                """))

            for column_name, definition in (
                ("species_name_zh_source", "VARCHAR(64) NULL AFTER species_name_zh"),
                (
                    "species_name_zh_review_status",
                    "VARCHAR(32) NULL AFTER species_name_zh_source",
                ),
            ):
                exists = conn.execute(text("""
                    SELECT COUNT(*)
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'bacdive_record'
                      AND COLUMN_NAME = :column_name
                """), {"column_name": column_name}).scalar()
                if not exists:
                    conn.execute(text(
                        f"ALTER TABLE bacdive_record ADD COLUMN {column_name} {definition}"
                    ))

            species_index_exists = conn.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'bacdive_record'
                  AND INDEX_NAME = 'idx_bacdive_species_name'
            """)).scalar()
            if not species_index_exists:
                conn.execute(text("""
                    ALTER TABLE bacdive_record
                    ADD INDEX idx_bacdive_species_name (species_name)
                """))

            review_index_exists = conn.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'bacdive_record'
                  AND INDEX_NAME = 'idx_bacdive_zh_review_status'
            """)).scalar()
            if not review_index_exists:
                conn.execute(text("""
                    ALTER TABLE bacdive_record
                    ADD INDEX idx_bacdive_zh_review_status (species_name_zh_review_status)
                """))

            conn.execute(text("""
                UPDATE bacdive_record
                SET species_name_zh_source = COALESCE(species_name_zh_source, 'existing'),
                    species_name_zh_review_status = COALESCE(
                        species_name_zh_review_status,
                        'verified'
                    )
                WHERE COALESCE(LENGTH(TRIM(species_name_zh)), 0) > 0
            """))
            conn.execute(text("""
                UPDATE bacdive_record br
                JOIN strain s
                  ON LOWER(TRIM(br.species_name)) COLLATE utf8mb4_unicode_ci
                   = LOWER(TRIM(s.scientific_name)) COLLATE utf8mb4_unicode_ci
                 AND br.species_name_zh COLLATE utf8mb4_unicode_ci
                   = TRIM(s.name) COLLATE utf8mb4_unicode_ci
                SET br.species_name_zh_source = 'local_strain',
                    br.species_name_zh_review_status = 'verified'
                WHERE s.is_active = 1
                  AND COALESCE(LENGTH(TRIM(br.species_name_zh)), 0) > 0
            """))

            tables = conn.execute(text("""
                SELECT TABLE_NAME
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME IN ('bacdive_record', 'bacdive_strain_match')
                ORDER BY TABLE_NAME
            """)).fetchall()

    print("Created/verified tables:")
    for row in tables:
        print(f"- {row[0]}")
    return 0


if __name__ == "__main__":
    if os.name == "nt":
        import codecs

        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")
    raise SystemExit(main())
