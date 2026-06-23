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
        """获取层次化的分类数据"""
        # 获取所有唯一的大类（第0级）
        general_classes = db.session.query(
            SampleLite.class_general
        ).distinct().all()

        hierarchical_data = {}

        for general in general_classes:
            general_name = general[0]
            # 获取该大类下的所有一级分类
            levelone_classes = db.session.query(
                SampleLite.class_levelone
            ).filter_by(
                class_general=general_name
            ).distinct().all()

            hierarchical_data[general_name] = {}

            for levelone in levelone_classes:
                levelone_name = levelone[0]
                # 获取该一级分类下的所有二级分类
                leveltwo_classes = db.session.query(
                    SampleLite.class_leveltwo
                ).filter_by(
                    class_general=general_name,
                    class_levelone=levelone_name
                ).distinct().all()

                hierarchical_data[general_name][levelone_name] = [
                    leveltwo[0] for leveltwo in leveltwo_classes
                ]

        return hierarchical_data