import runpy
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / 'gunicorn.conf.py'


def test_gunicorn_keeps_slow_uploads_alive():
    settings = runpy.run_path(str(CONFIG))

    # Sync workers are killed after `timeout` seconds of one request, which
    # cut off slow photo uploads; threads and a long timeout avoid that.
    assert settings['worker_class'] == 'gthread'
    assert settings['threads'] >= 2
    assert settings['timeout'] >= 120
