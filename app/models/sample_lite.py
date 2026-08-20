from app.extensions import db


class SampleLite(db.Model):
    __tablename__ = 'sample_lite'

    id = db.Column(db.Integer, primary_key=True)
    class_general = db.Column(db.String(100), nullable=False, comment='分类')
    class_levelone = db.Column(db.String(100), nullable=False, comment='一级分类')
    class_leveltwo = db.Column(db.String(100), nullable=False, comment='二级分类')
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # 添加索引以提高查询性能
    __table_args__ = (
        db.Index('idx_general', 'class_general'),
        db.Index('idx_levelone', 'class_levelone'),
        db.Index('idx_leveltwo', 'class_leveltwo'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'class_general': self.class_general,
            'class_levelone': self.class_levelone,
            'class_leveltwo': self.class_leveltwo
        }

    @staticmethod
    def get_hierarchical_data():
        """获取层次化的分类数据（单次查询 + 内存组装，避免 N+1）。"""
        rows = db.session.query(
            SampleLite.class_general,
            SampleLite.class_levelone,
            SampleLite.class_leveltwo,
        ).distinct().order_by(
            SampleLite.class_general,
            SampleLite.class_levelone,
            SampleLite.class_leveltwo,
        ).all()

        hierarchical_data = {}
        for general, levelone, leveltwo in rows:
            general_name = general
            levelone_name = levelone
            hierarchical_data.setdefault(general_name, {}).setdefault(
                levelone_name, []
            )
            if leveltwo not in hierarchical_data[general_name][levelone_name]:
                hierarchical_data[general_name][levelone_name].append(leveltwo)
        return hierarchical_data