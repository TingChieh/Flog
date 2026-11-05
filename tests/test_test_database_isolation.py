import os
import subprocess
import sys


def test_test_suite_forces_sqlite_when_database_url_is_preconfigured():
    env = os.environ.copy()
    env.pop('TEST_DATABASE_URL', None)
    env['DATABASE_URL'] = 'mysql+pymysql://example.invalid/flog'

    result = subprocess.run(
        [sys.executable, '-c',
         'import tests.conftest; print(tests.conftest.app.config['
         '"SQLALCHEMY_DATABASE_URI"])'],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip().splitlines()[-1] == 'sqlite://'


def test_explicit_test_database_url_is_used():
    env = os.environ.copy()
    env['DATABASE_URL'] = 'mysql+pymysql://example.invalid/production'
    env['TEST_DATABASE_URL'] = 'sqlite:///explicit-test.sqlite'
    result = subprocess.run(
        [sys.executable, '-c',
         'import tests.conftest; print(tests.conftest.app.config['
         '"SQLALCHEMY_DATABASE_URI"])'],
        cwd=os.getcwd(), env=env, capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip().splitlines()[-1] == 'sqlite:///explicit-test.sqlite'
