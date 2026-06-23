from app.extensions import db

class DetectResult(db.Model):
    __tablename__ = "detect_result"

    id = db.Column(db.Integer, primary_key=True)
    strain_name = db.Column(db.String(100))
    confidence = db.Column(db.Float)
    x1 = db.Column(db.Integer)
    y1 = db.Column(db.Integer)
    x2 = db.Column(db.Integer)
    y2 = db.Column(db.Integer)
    is_final = db.Column(db.Boolean, default=False)

    task_id = db.Column(db.Integer, db.ForeignKey("detect_task.id"), nullable=False)
