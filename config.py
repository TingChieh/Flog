import os
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'mysql+pymysql://root:ogihana77**@localhost/flog'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAIL_SERVER = 'smtp.hedwi.net'
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    # MAIL_USE_TLS = True
    MAIL_USERNAME = 'admin@aisaka.cc'
    MAIL_PASSWORD = 'bad06669c6eeca005caf5c3a6b3efd1d'
    ADMINS = ['admin@aisaka.cc']
    LANGUAGES = ['en', 'zh']
    MS_TRANSLATOR_KEY = 'b699690623de4f8a9bfcb051c2db0145'
    ELASTICSEARCH_URL = os.environ.get('ELASTICSEARCH_URL') or 'http://localhost:9200'
    CKEDITOR_FILE_UPLOADER = 'upload'
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    POSTS_PER_PAGE = 10
    APPID = os.environ.get('APPID') or '20240829002135964'
    BD_TRANSLATOR_KEY = os.environ.get('MS_TRANSLATOR_KEY') or '7glokqSIlBtMpKacGOfZ'