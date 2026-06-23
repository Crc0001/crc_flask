import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = "dev-secret-key"
    SQLALCHEMY_DATABASE_URI = (
        "mysql+pymysql://user:password@localhost:3306/crc_flaskdb?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
