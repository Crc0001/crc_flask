from app.extensions import db

class Sample(db.Model):
    __tablename__ = "sample"

    id = db.Column(db.Integer, primary_key=True)
    sample_code = db.Column(db.String(50), unique=True)
    collect_date = db.Column(db.DateTime)
    collector = db.Column(db.String(50))
    collect_location = db.Column(db.String(100))
    final_strain_name = db.Column(db.String(100))
    final_confidence = db.Column(db.Float)
    last_detect_time = db.Column(db.DateTime)
    last_detect_count = db.Column(db.Integer, default=0)
    mass_spectrum = db.Column(db.LargeBinary)

    tasks = db.relationship("DetectTask",backref="sample",lazy="dynamic",cascade="all, delete-orphan",
                            foreign_keys="DetectTask.sample_id")

    def __repr__(self):
        return f"<Sample {self.sample_code}>"