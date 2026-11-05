"""Boot-time configuration behavior."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_config_loads_project_dotenv_without_overriding_process_environment(tmp_path):
    """Catch production boots that ignore saved settings or override deployment env."""
    (tmp_path / '.env').write_text(
        'SECRET_KEY=from-project-dotenv\n'
        'MAIL_PORT=2525\n'
        'MAIL_SERVER=smtp.dotenv.example\n',
        encoding='utf-8',
    )
    shutil.copy2(Path(__file__).parents[1] / 'config.py', tmp_path / 'config.py')
    environment = dict(os.environ)
    environment.pop('SECRET_KEY', None)
    environment.pop('MAIL_SERVER', None)
    environment['MAIL_PORT'] = '587'

    result = subprocess.run(
        [
            sys.executable,
            '-c',
            ('import json; from config import Config; '
             'print(json.dumps({"secret": Config.SECRET_KEY, '
             '"mail_port": Config.MAIL_PORT, "mail_server": Config.MAIL_SERVER}))'),
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        'secret': 'from-project-dotenv',
        'mail_port': 587,
        'mail_server': 'smtp.dotenv.example',
    }


def test_relative_upload_folder_resolves_from_project_root(tmp_path):
    """Catch uploads saved and served from different directories."""
    shutil.copy2(Path(__file__).parents[1] / 'config.py', tmp_path / 'config.py')
    environment = dict(os.environ)
    environment['UPLOAD_FOLDER'] = 'instance/uploads'
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            '-c',
            f'import sys; sys.path.insert(0, {str(tmp_path)!r}); '
            'from config import Config; print(Config.UPLOAD_FOLDER)',
        ],
        cwd=elsewhere,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert Path(result.stdout.strip()) == tmp_path.resolve() / 'instance' / 'uploads'
