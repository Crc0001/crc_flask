from app.extensions import db


class StrainTaxonomy(db.Model):
    __tablename__ = "strain_taxonomy"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    strain_rank = db.Column(db.String(128))
    parent_id = db.Column(db.Integer, db.ForeignKey("strain_taxonomy.id"))
    description = db.Column(db.Text)

    parent = db.relationship("StrainTaxonomy", remote_side=[id], backref="children")


class Strain(db.Model):
    __tablename__ = "strain"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    scientific_name = db.Column(db.String(255))
    alias = db.Column(db.String(255))
    strain_code = db.Column(db.String(255))
    category = db.Column(db.String(255))
    taxonomy_id = db.Column(db.Integer, db.ForeignKey("strain_taxonomy.id"))
    main_image = db.Column(db.String(512))
    fingerprint_image = db.Column(db.String(512))
    gram_stain_image = db.Column(db.String(512))
    summary = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)

    taxonomy = db.relationship("StrainTaxonomy", backref="strains")
    morphology = db.relationship("StrainMorphology", back_populates="strain", uselist=False)
    growth_cycles = db.relationship(
        "StrainGrowthCycle",
        back_populates="strain",
        order_by="StrainGrowthCycle.day_number"
    )
    media_links = db.relationship("StrainMedium", back_populates="strain")
    sources = db.relationship("StrainSource", back_populates="strain")
    strain_16s_records = db.relationship("Strain16S", back_populates="strain", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Strain {self.name or self.scientific_name}>"


class StrainSource(db.Model):
    __tablename__ = "strain_source"

    id = db.Column(db.Integer, primary_key=True)
    strain_id = db.Column(db.Integer, db.ForeignKey("strain.id"), nullable=False)
    location = db.Column(db.String(255))

    strain = db.relationship("Strain", back_populates="sources")


class Strain16S(db.Model):
    __tablename__ = "strain_16s"

    id = db.Column(db.Integer, primary_key=True)
    strain_id = db.Column(db.Integer, db.ForeignKey("strain.id"), nullable=False)
    strain_16s = db.Column(db.Text)

    strain = db.relationship("Strain", back_populates="strain_16s_records")


class StrainMorphology(db.Model):
    __tablename__ = "strain_morphology"

    id = db.Column(db.Integer, primary_key=True)
    strain_id = db.Column(db.Integer, db.ForeignKey("strain.id"))
    colony_size = db.Column(db.String(128))
    colony_shape = db.Column(db.String(128))
    colony_edge = db.Column(db.String(128))
    colony_color = db.Column(db.String(128))
    colony_texture = db.Column(db.String(128))
    colony_elevation = db.Column(db.String(128))
    colony_opacity = db.Column(db.String(128))
    cell_shape = db.Column(db.String(128))

    strain = db.relationship("Strain", back_populates="morphology")


class StrainGrowthCycle(db.Model):
    __tablename__ = "strain_growth_cycle"

    id = db.Column(db.Integer, primary_key=True)
    strain_id = db.Column(db.Integer, db.ForeignKey("strain.id"))
    day_number = db.Column(db.Integer)
    image_path = db.Column(db.String(512))
    temperature = db.Column(db.String(64))
    description = db.Column(db.Text)

    strain = db.relationship("Strain", back_populates="growth_cycles")


class Medium(db.Model):
    __tablename__ = "medium"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    medium_code = db.Column(db.String(255))
    culture_time = db.Column(db.String(10))
    temperature = db.Column(db.String(64))
    created_at = db.Column(db.DateTime)

    strain_links = db.relationship("StrainMedium", back_populates="medium")


class StrainMedium(db.Model):
    __tablename__ = "strain_medium"

    strain_id = db.Column(db.Integer, db.ForeignKey("strain.id"), primary_key=True)
    medium_id = db.Column(db.Integer, db.ForeignKey("medium.id"), primary_key=True)
    is_recommended = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)

    strain = db.relationship("Strain", back_populates="media_links")
    medium = db.relationship("Medium", back_populates="strain_links")
