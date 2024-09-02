import os
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'mysql+pymysql://root:ogihana77**@localhost/flask'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAIL_SERVER = 'smtp.hedwi.net'
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    # MAIL_USE_TLS = True
    MAIL_USERNAME = 'admin@aisaka.cc'
    MAIL_PASSWORD = 'bad06669c6eeca005caf5c3a6b3efd1d'
    ADMINS = ['admin@aisaka.cc']
    LANGUAGES = ['en', 'zh']
    MS_TRANSLATOR_KEY = os.environ.get('MS_TRANSLATOR_KEY')
    POSTS_PER_PAGE = 1