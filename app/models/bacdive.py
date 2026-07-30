from app.extensions import db


class BacdiveRecord(db.Model):
    __tablename__ = "bacdive_record"

    id = db.Column(db.Integer, primary_key=True)
    bacdive_id = db.Column(db.Integer, nullable=False, unique=True)
    dsm_number = db.Column(db.String(64))
    doi = db.Column(db.String(255))

    domain_name = db.Column(db.String(128))
    phylum_name = db.Column(db.String(128))
    class_name = db.Column(db.String(128))
    order_name = db.Column(db.String(128))
    family_name = db.Column(db.String(128))
    genus_name = db.Column(db.String(128))
    species_name = db.Column(db.String(255))
    species_name_zh = db.Column(db.String(255), index=True)
    species_name_zh_source = db.Column(db.String(64))
    species_name_zh_review_status = db.Column(db.String(32), index=True)
    full_scientific_name = db.Column(db.String(255))
    strain_designation = db.Column(db.String(255))
    type_strain = db.Column(db.String(64))

    ncbi_tax_id = db.Column(db.Integer)
    ncbi_matching_level = db.Column(db.String(64))
    description = db.Column(db.Text)
    keywords = db.Column(db.String(255))
    strain_history = db.Column(db.Text)

    culture_medium = db.Column(db.JSON)
    culture_temp = db.Column(db.JSON)
    culture_ph = db.Column(db.JSON)
    morphology = db.Column(db.JSON)
    physiology = db.Column(db.JSON)
    isolation_info = db.Column(db.JSON)
    safety_info = db.Column(db.JSON)
    sequence_info = db.Column(db.JSON)
    literature_info = db.Column(db.JSON)
    raw_json = db.Column(db.JSON, nullable=False)

    source_file = db.Column(db.String(255))
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)

    environment_matches = db.relationship(
        "BacdiveStrainMatch",
        back_populates="bacdive_record",
        cascade="all, delete-orphan",
    )


class BacdiveStrainMatch(db.Model):
    __tablename__ = "bacdive_strain_match"

    id = db.Column(db.Integer, primary_key=True)
    strain_id = db.Column(db.Integer, db.ForeignKey("strain.id"), nullable=False)
    bacdive_record_id = db.Column(
        db.Integer,
        db.ForeignKey("bacdive_record.id"),
        nullable=False,
    )
    match_method = db.Column(db.String(64))
    match_score = db.Column(db.Float)
    matched_by = db.Column(db.String(255))
    created_at = db.Column(db.DateTime)

    strain = db.relationship("Strain", backref="bacdive_matches")
    bacdive_record = db.relationship("BacdiveRecord", back_populates="environment_matches")
