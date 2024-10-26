# A flask python web application depends on flask

Demo: https://flog.aisaka.cc

## Installation



Clone the repo:

```
$ git git@github.com:TingChieh/Flog.git
$ cd Flog
```

​    

Create & activate virtual env then install dependency:

with venv + pip:

```
$ python3 -m venv .venv  # use `python ...` on Windows
$ source .venv/bin/activate  # use `.venv\Scripts\activate` on Windows
$ pip install -r requirements.txt
```

You need to write a config.py:

```
import os
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'mysql+pymysql://root:password@localhost/flog'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'example.com'
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    # MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME') or 'admin@example.com'
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD') or 'mailpassword'
    ADMINS = os.environ.get('ADMINS') or ['admin@example.com']
    LANGUAGES = ['en', 'zh']
    MS_TRANSLATOR_KEY = os.environ.get('MS_TRANSLATOR_KEY') or 'KEY'
    ELASTICSEARCH_URL = os.environ.get('ELASTICSEARCH_URL') or 'http://localhost:9200'
    CKEDITOR_FILE_UPLOADER = 'upload'
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    POSTS_PER_PAGE = 10
    APPID = os.environ.get('APPID') or 'APPID'
    BD_TRANSLATOR_KEY = os.environ.get('MS_TRANSLATOR_KEY') or 'BD_KEY'
```

Test account:

- username: `susan`
- password: `cat`

## License



This project is licensed under the MIT License (see the [LICENSE](https://github.com/greyli/greybook/blob/main/LICENSE) file for details).
