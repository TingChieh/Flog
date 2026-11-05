import os
import subprocess
import sys

import pytest


def config_for(level):
    env = os.environ.copy()
    env['DATABASE_URL'] = 'mysql+pymysql://user:pass@localhost/example'
    if level is None:
        env.pop('DB_ISOLATION_LEVEL', None)
    else:
        env['DB_ISOLATION_LEVEL'] = level
    return subprocess.run([sys.executable, '-c',
        'from config import Config; print(Config.SQLALCHEMY_ENGINE_OPTIONS)'],
        env=env, capture_output=True, text=True)


@pytest.mark.parametrize('level', [None, ''])
def test_isolation_defaults_to_database_setting(level):
    result = config_for(level)
    assert result.returncode == 0
    assert result.stdout.strip() == '{}'


@pytest.mark.parametrize('level', ['READ COMMITTED', 'READ UNCOMMITTED', 'REPEATABLE READ', 'SERIALIZABLE', 'AUTOCOMMIT'])
def test_isolation_accepts_supported_values(level):
    result = config_for(level)
    assert result.returncode == 0
    assert result.stdout.strip() == repr({'isolation_level': level})


def test_isolation_rejects_invalid_value():
    result = config_for('INVALID')
    assert result.returncode != 0
    assert 'DB_ISOLATION_LEVEL' in result.stderr
