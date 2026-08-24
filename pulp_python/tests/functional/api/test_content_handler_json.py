"""Content-app JSON via Accept: application/json (PythonDistribution.content_handler_json).

These tests hit the content app, not the DRF ``/pypi/`` API. They require pulpcore
Phase 1 (issue 7887): ``Distribution.content_handler_json`` plus Handler Accept
negotiation. When CI pulpcore is unpatched, skip — unit tests still cover the
handler return values.
"""

from importlib.util import find_spec
from pathlib import Path
from urllib.parse import urljoin

import pytest
import requests

from pulp_python.tests.functional.constants import (
    PYPI_SIMPLE_V1_JSON,
    PYTHON_WHEEL_FILENAME,
    PYTHON_XS_PROJECT_SPECIFIER,
)

JSON_ACCEPT = {"Accept": "application/json"}


def _pulpcore_content_app_json_enabled():
    """True when pulpcore will invoke Distribution.content_handler_json on JSON Accept.

    Inspect source files instead of importing Django models, which are not ready
    during pytest collection. Use find_spec so editable installs are resolved.
    """
    handler = find_spec("pulpcore.content.handler")
    if not handler or not handler.origin:
        return False
    handler_path = Path(handler.origin)
    publication_path = handler_path.resolve().parents[1] / "app" / "models" / "publication.py"
    try:
        handler_src = handler_path.read_text()
        publication_src = publication_path.read_text()
    except OSError:
        return False
    return "def negotiate_json" in handler_src and "def content_handler_json" in publication_src


pytestmark = pytest.mark.skipif(
    not _pulpcore_content_app_json_enabled(),
    reason=(
        "Requires pulpcore content-app Accept negotiation (Handler.negotiate_json and "
        "Distribution.content_handler_json from pulpcore issue 7887). Unit tests cover "
        "PythonDistribution.content_handler_json without that pulpcore change."
    ),
)


def _content_url(pulp_content_url, distro, rel=""):
    return urljoin(pulp_content_url, f"{distro.base_path}/{rel}")


@pytest.mark.parallel
def test_content_app_simple_index_and_detail_json(
    python_remote_factory, python_repo_with_sync, python_distribution_factory, pulp_content_url
):
    """``.../simple/`` and ``.../simple/<name>/`` return PEP 691 Simple JSON."""
    remote = python_remote_factory(includes=PYTHON_XS_PROJECT_SPECIFIER)
    repo = python_repo_with_sync(remote)
    distro = python_distribution_factory(repository=repo)

    index = requests.get(_content_url(pulp_content_url, distro, "simple/"), headers=JSON_ACCEPT)
    assert index.status_code == 200
    assert PYPI_SIMPLE_V1_JSON in index.headers["Content-Type"]
    index_body = index.json()
    assert index_body["meta"]["api-version"] == "1.1"
    names = [project["name"] for project in index_body["projects"]]
    assert any("shelf" in name.lower() for name in names)

    detail = requests.get(
        _content_url(pulp_content_url, distro, "simple/shelf-reader/"), headers=JSON_ACCEPT
    )
    assert detail.status_code == 200
    assert PYPI_SIMPLE_V1_JSON in detail.headers["Content-Type"]
    detail_body = detail.json()
    assert detail_body["name"] == "shelf-reader"
    assert detail_body["files"]
    assert detail_body["versions"]
    filenames = [f["filename"] for f in detail_body["files"]]
    assert PYTHON_WHEEL_FILENAME in filenames or any("shelf" in f for f in filenames)


@pytest.mark.parallel
def test_content_app_pypi_json_without_json_suffix(
    python_remote_factory, python_repo_with_sync, python_distribution_factory, pulp_content_url
):
    """``.../pypi/<name>/`` returns PyPI JSON without the ``/json`` URL convention."""
    remote = python_remote_factory(includes=PYTHON_XS_PROJECT_SPECIFIER)
    repo = python_repo_with_sync(remote)
    distro = python_distribution_factory(repository=repo)

    response = requests.get(
        _content_url(pulp_content_url, distro, "pypi/shelf-reader/"), headers=JSON_ACCEPT
    )
    assert response.status_code == 200
    assert "application/json" in response.headers["Content-Type"]
    body = response.json()
    assert "info" in body
    assert "releases" in body
    assert "urls" in body
    assert "shelf" in body["info"]["name"].lower()


@pytest.mark.parallel
def test_content_app_distro_root_is_generic_listing(
    python_remote_factory, python_repo_with_sync, python_distribution_factory, pulp_content_url
):
    """Distribution root still uses pulpcore's generic JSON listing, not PyPI/Simple JSON."""
    remote = python_remote_factory(includes=PYTHON_XS_PROJECT_SPECIFIER)
    repo = python_repo_with_sync(remote)
    distro = python_distribution_factory(repository=repo)

    response = requests.get(_content_url(pulp_content_url, distro), headers=JSON_ACCEPT)
    assert response.status_code == 200
    assert "application/json" in response.headers["Content-Type"]
    body = response.json()
    assert "packages" in body
    assert "projects" not in body
    assert "info" not in body


@pytest.mark.parallel
def test_content_app_artifact_stays_binary(
    python_remote_factory, python_repo_with_sync, python_distribution_factory, pulp_content_url
):
    """Concrete package artifacts stay binary even when Accept prefers JSON."""
    remote = python_remote_factory(includes=PYTHON_XS_PROJECT_SPECIFIER, policy="immediate")
    repo = python_repo_with_sync(remote)
    distro = python_distribution_factory(repository=repo)

    response = requests.get(
        _content_url(pulp_content_url, distro, PYTHON_WHEEL_FILENAME), headers=JSON_ACCEPT
    )
    assert response.status_code == 200
    assert "application/json" not in response.headers.get("Content-Type", "")
    assert response.content[:2] == b"PK"  # zip/wheel local file header
