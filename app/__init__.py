from flask import Flask
from app.extensions import db
from app.routes.main import main_bp
from app.routes.ai_detection import ai_detection_bp
from app.routes.strain_db import strain_db_bp
from app.routes.analysis import analysis_bp
from app.routes.strain_showcase import strain_showcase_bp
from app.routes.maldi_matching import maldi_matching_bp

def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = "mysql+pymysql://root:123456@localhost/crc_ai"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)


    app.register_blueprint(main_bp)
    app.register_blueprint(ai_detection_bp)
    app.register_blueprint(strain_db_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(strain_showcase_bp)
    app.register_blueprint(maldi_matching_bp)

    return app
