import runpy
from pathlib import Path

import pytest

CONFIG = Path(__file__).resolve().parent.parent / 'gunicorn.conf.py'


def load_config(monkeypatch, web_concurrency=None):
    if web_concurrency is None:
        monkeypatch.delenv('WEB_CONCURRENCY', raising=False)
    else:
        monkeypatch.setenv('WEB_CONCURRENCY', web_concurrency)
    return runpy.run_path(str(CONFIG))


def test_several_requests_are_served_at_once_by_default(monkeypatch):
    config = load_config(monkeypatch)

    # One slow request mustn't stop the site: 2 workers with 4 threads each
    assert config['workers'] == 2
    assert config['worker_class'] == 'gthread'
    assert config['threads'] == 4
    assert config['bind'] == '0.0.0.0:8000'


def test_worker_count_from_web_concurrency(monkeypatch):
    assert load_config(monkeypatch, '5')['workers'] == 5


def test_worker_count_that_is_not_a_number_fails_at_startup(monkeypatch):
    with pytest.raises(ValueError):
        load_config(monkeypatch, 'many')


def test_production_command_leaves_the_numbers_to_the_config_file():
    compose = (CONFIG.parent / 'docker-compose-prod.yml').read_text()

    # Flags on the command line would win over gunicorn.conf.py and WEB_CONCURRENCY
    assert 'exec gunicorn project.wsgi"\n' in compose
