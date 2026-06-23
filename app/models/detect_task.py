from app.extensions import db

class DetectTask(db.Model):
    __tablename__ = "detect_task"

    id = db.Column(db.Integer, primary_key=True)
    image_path = db.Column(db.String(255))
    result_image_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime)
    sample_code = db.Column(db.String(50))
    collect_date = db.Column(db.DateTime)
    location = db.Column(db.String(100))
    detect_count = db.Column(db.Integer, default=0)

    sample_id = db.Column(db.Integer,db.ForeignKey("sample.id"), nullable=False)

    results = db.relationship("DetectResult", backref="task", lazy="dynamic", cascade="all, delete-orphan"
                             )