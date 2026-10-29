import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Dependabot updates the compose files but not the services in the workflow
FILES = ['docker-compose-dev.yml', 'docker-compose-prod.yml', '.github/workflows/django.yml']


def pins(image):
    return {
        name: re.findall(rf'image: {image}:(\S+)', (ROOT / name).read_text())
        for name in FILES
    }


@pytest.mark.parametrize('image', ['postgres', 'redis'])
def test_dev_prod_and_ci_use_the_same_image_version(image):
    found = pins(image)

    assert all(len(tags) == 1 for tags in found.values()), found
    assert len({tags[0] for tags in found.values()}) == 1, found
