from app.extensions import db
from sqlalchemy.dialects.mysql import MEDIUMTEXT


class SilvaSsuSequence(db.Model):
    __tablename__ = "silva_ssu_sequence"

    id = db.Column(db.BigInteger, primary_key=True)
    sequence_identifier = db.Column(db.String(191), nullable=False, unique=True)
    accession = db.Column(db.String(128), nullable=False, index=True)
    organism_name = db.Column(db.String(512))
    taxonomy = db.Column(db.Text, nullable=False)
    domain_name = db.Column(db.String(128), index=True)
    phylum_name = db.Column(db.String(128), index=True)
    class_name = db.Column(db.String(128))
    order_name = db.Column(db.String(128))
    family_name = db.Column(db.String(128))
    genus_name = db.Column(db.String(128), index=True)
    species_name = db.Column(db.String(255))
    sequence = db.Column(db.Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False)
    sequence_length = db.Column(db.Integer, nullable=False, index=True)
    silva_release = db.Column(db.String(32), nullable=False)
    source_file = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.current_timestamp())
    updated_at = db.Column(
        db.DateTime,
        server_default=db.func.current_timestamp(),
        onupdate=db.func.current_timestamp(),
    )
