from app.extensions import db


class MaldiReference(db.Model):
    """MALDI-TOF 质谱参考谱库模型"""
    __tablename__ = 'maldi_reference'

    id = db.Column(db.Integer, primary_key=True)
    strain_id = db.Column(db.Integer, db.ForeignKey('strain.id'), nullable=False)
    sample_id = db.Column(db.String(100))
    peaks = db.Column(db.JSON, nullable=False)
    peak_count = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    strain = db.relationship('Strain', backref='maldi_references')

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'strain_id': self.strain_id,
            'strain_name': self.strain.name if self.strain else None,
            'scientific_name': self.strain.scientific_name if self.strain else None,
            'sample_id': self.sample_id,
            'peak_count': self.peak_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f'<MaldiReference {self.id}: strain_id={self.strain_id}, sample_id={self.sample_id}>'
