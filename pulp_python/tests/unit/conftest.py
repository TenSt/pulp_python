import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pulpcore.app.settings")


def pytest_configure(config):
    django.setup()
