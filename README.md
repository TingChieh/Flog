# A flask python web application depends on flask

Demo: https://flog.aisaka.cc

## Installation



Clone the repo:

```
$ git git@github.com:TingChieh/flask-study.git
$ cd flask-studu
```

​    

Create & activate virtual env then install dependency:

with venv + pip:

```
$ python3 -m venv .venv  # use `python ...` on Windows
$ source .venv/bin/activate  # use `.venv\Scripts\activate` on Windows
$ pip install -r requirements.txt
```

​    

or with PDM (you need to [install PDM](https://pdm.fming.dev/latest/#installation) first):

```
$ pdm install
$ source .venv/bin/activate  # use `.venv\Scripts\activate` on Windows
```

​    

Generate data then run the application:

```
$ flask lorem
$ flask run
* Running on http://127.0.0.1:5000/
```

​    

Test account:

- username: `susan`
- password: `cat`

## License



This project is licensed under the MIT License (see the [LICENSE](https://github.com/greyli/greybook/blob/main/LICENSE) file for details).