from urllib.parse import urljoin

import pytest
import requests

from pulp_python.tests.functional.constants import (
    PYPI_SIMPLE_V1_JSON,
    PYTHON_FIXTURES_URL,
    TWINE_EGG_FILENAME,
    TWINE_EGG_URL,
    TWINE_WHEEL_FILENAME,
    TWINE_WHEEL_URL,
)

TWINE_NAME = "twine"
TWINE_VERSION = "5.1.0"

TWINE_500_WHEEL_FILENAME = "twine-5.0.0-py3-none-any.whl"
TWINE_500_WHEEL_URL = urljoin(urljoin(PYTHON_FIXTURES_URL, "packages/"), TWINE_500_WHEEL_FILENAME)


def test_yank_and_unyank(
    delete_orphans_pre,
    monitor_task,
    python_bindings,
    python_content_factory,
    python_content_summary,
    python_distribution_factory,
    python_repo_factory,
):
    """
    Yank and unyank lifecycle including idempotency and reason update checks.

    Every yank/unyank that changes state creates a new repo version.
    Repeating the same operation with the same reason is a no-op (no new version).
    Re-yanking with a different reason updates the reason and creates a new version.
    """
    content_sdist = python_content_factory(TWINE_EGG_FILENAME, url=TWINE_EGG_URL)
    content_whl = python_content_factory(TWINE_WHEEL_FILENAME, url=TWINE_WHEEL_URL)
    repo = python_repo_factory()
    body = {"add_content_units": [content_sdist.pulp_href, content_whl.pulp_href]}
    monitor_task(python_bindings.RepositoriesPythonApi.modify(repo.pulp_href, body).task)
    repo = python_bindings.RepositoriesPythonApi.read(repo.pulp_href)
    distro = python_distribution_factory(repository=repo)
    version_1 = repo.latest_version_href

    # 1. Yank
    response = python_bindings.PypiYankApi.yank(
        path=distro.base_path,
        yank={"name": TWINE_NAME, "version": TWINE_VERSION, "yanked_reason": "broken"},
    )
    monitor_task(response.task)

    repo = python_bindings.RepositoriesPythonApi.read(repo.pulp_href)
    version_2 = repo.latest_version_href
    assert version_2 != version_1
    summary = python_content_summary(repository=repo, version=2)
    assert summary.added["python.python_yank"]["count"] == 1

    # Check Simple API JSON - yanked files should have yanked reason
    simple_url = urljoin(distro.base_url, f"simple/{TWINE_NAME}")
    response = requests.get(simple_url, headers={"Accept": PYPI_SIMPLE_V1_JSON})
    assert response.json()["files"][0]["yanked"] == "broken"
    assert response.json()["files"][1]["yanked"] == "broken"

    # Check Simple API HTML - data-yanked attribute should be present
    response = requests.get(simple_url)
    assert response.text.count('data-yanked="broken"') == 2

    # Check PyPI Metadata API - yanked info in metadata
    pypi_url = urljoin(distro.base_url, f"pypi/{TWINE_NAME}/json")
    response = requests.get(pypi_url)
    data = response.json()
    assert data["info"]["yanked"] is True
    assert data["info"]["yanked_reason"] == "broken"
    for f in data["releases"][TWINE_VERSION]:
        assert f["yanked"] is True
        assert f["yanked_reason"] == "broken"
    for f in data["urls"]:
        assert f["yanked"] is True
        assert f["yanked_reason"] == "broken"

    # Yank again with same reason - idempotent, no new repo version
    response = python_bindings.PypiYankApi.yank(
        path=distro.base_path,
        yank={"name": TWINE_NAME, "version": TWINE_VERSION, "yanked_reason": "broken"},
    )
    monitor_task(response.task)

    repo = python_bindings.RepositoriesPythonApi.read(repo.pulp_href)
    assert repo.latest_version_href == version_2

    # Yank again with different reason - updates the reason
    response = python_bindings.PypiYankApi.yank(
        path=distro.base_path,
        yank={"name": TWINE_NAME, "version": TWINE_VERSION, "yanked_reason": "security fix"},
    )
    monitor_task(response.task)

    repo = python_bindings.RepositoriesPythonApi.read(repo.pulp_href)
    version_3 = repo.latest_version_href
    assert version_3 != version_2

    # Simple API should show updated reason
    response = requests.get(simple_url, headers={"Accept": PYPI_SIMPLE_V1_JSON})
    assert response.json()["files"][0]["yanked"] == "security fix"
    assert response.json()["files"][1]["yanked"] == "security fix"

    response = requests.get(simple_url)
    assert response.text.count('data-yanked="security fix"') == 2

    # 2. Unyank
    response = python_bindings.PypiUnyankApi.unyank(
        path=distro.base_path, yank={"name": TWINE_NAME, "version": TWINE_VERSION}
    )
    monitor_task(response.task)

    repo = python_bindings.RepositoriesPythonApi.read(repo.pulp_href)
    version_4 = repo.latest_version_href
    assert version_4 != version_3
    summary = python_content_summary(repository=repo, version=4)
    assert summary.removed["python.python_yank"]["count"] == 1

    # Check Simple API JSON - yanked should be False after unyank
    response = requests.get(simple_url, headers={"Accept": PYPI_SIMPLE_V1_JSON})
    assert response.json()["files"][0]["yanked"] is False
    assert response.json()["files"][1]["yanked"] is False

    # Check Simple API HTML - data-yanked attribute should not be present
    response = requests.get(simple_url)
    assert "data-yanked" not in response.text

    # Check PyPI Metadata API - yanked should be False after unyank
    response = requests.get(pypi_url)
    data = response.json()
    assert data["info"]["yanked"] is False
    assert data["info"]["yanked_reason"] is None
    for f in data["releases"][TWINE_VERSION]:
        assert f["yanked"] is False
        assert f["yanked_reason"] is None
    for f in data["urls"]:
        assert f["yanked"] is False
        assert f["yanked_reason"] is None

    # Unyank again - idempotent, no new repo version
    response = python_bindings.PypiUnyankApi.unyank(
        path=distro.base_path, yank={"name": TWINE_NAME, "version": TWINE_VERSION}
    )
    monitor_task(response.task)

    repo = python_bindings.RepositoriesPythonApi.read(repo.pulp_href)
    assert repo.latest_version_href == version_4


def test_yank_sync(
    delete_orphans_pre,
    python_remote_factory,
    python_repo_with_sync,
    python_content_summary,
    python_distribution_factory,
):
    """
    Syncing a yanked package from upstream creates a PackageYank marker.
    """
    remote = python_remote_factory(includes=[f"{TWINE_NAME}=={TWINE_VERSION}"])
    repo = python_repo_with_sync(remote)
    distro = python_distribution_factory(repository=repo)

    # Sync should have created a yank marker for twine 5.1.0
    summary = python_content_summary(repository=repo, version=1)
    assert summary.added["python.python"]["count"] == 2
    assert summary.added["python.python_yank"]["count"] == 1

    # Check Simple API JSON - yanked files should have yanked reason
    simple_url = urljoin(distro.base_url, f"simple/{TWINE_NAME}")
    response = requests.get(simple_url, headers={"Accept": PYPI_SIMPLE_V1_JSON})
    assert response.json()["files"][0]["yanked"] == "https://github.com/pypa/twine/issues/1125"
    assert response.json()["files"][1]["yanked"] == "https://github.com/pypa/twine/issues/1125"

    # Check Simple API HTML - data-yanked attribute should be present
    response = requests.get(simple_url)
    assert response.text.count("data-yanked=") == 2


@pytest.mark.parallel
def test_partial_yank(
    monitor_task,
    python_bindings,
    python_content_factory,
    python_content_summary,
    python_distribution_factory,
    python_repo_factory,
):
    """
    Yanking one version does not affect other versions of the same package.
    """
    content_510 = python_content_factory(TWINE_WHEEL_FILENAME, url=TWINE_WHEEL_URL)
    content_500 = python_content_factory(TWINE_500_WHEEL_FILENAME, url=TWINE_500_WHEEL_URL)

    repo = python_repo_factory()
    body = {"add_content_units": [content_510.pulp_href, content_500.pulp_href]}
    monitor_task(python_bindings.RepositoriesPythonApi.modify(repo.pulp_href, body).task)
    distro = python_distribution_factory(repository=repo)

    response = python_bindings.PypiYankApi.yank(
        path=distro.base_path,
        yank={"name": TWINE_NAME, "version": TWINE_VERSION, "yanked_reason": "broken 5.1.0"},
    )
    monitor_task(response.task)

    summary = python_content_summary(repository=repo, version=2)
    assert summary.added["python.python_yank"]["count"] == 1
    assert summary.present["python.python_yank"]["count"] == 1

    # Check Simple API JSON - yanked files should have yanked reason
    simple_url = urljoin(distro.base_url, f"simple/{TWINE_NAME}")
    response = requests.get(simple_url, headers={"Accept": PYPI_SIMPLE_V1_JSON})
    data = response.json()
    file_510 = next(f for f in data["files"] if f["filename"] == TWINE_WHEEL_FILENAME)
    file_500 = next(f for f in data["files"] if f["filename"] == TWINE_500_WHEEL_FILENAME)
    assert file_510["yanked"] == "broken 5.1.0"
    assert file_500["yanked"] is False


@pytest.mark.parallel
def test_yank_isolation_across_repositories(
    monitor_task,
    python_bindings,
    python_content_factory,
    python_content_summary,
    python_distribution_factory,
    python_repo_factory,
):
    """
    Yanking in one repo does not affect another repo with the same content.
    """
    content = python_content_factory(TWINE_WHEEL_FILENAME, url=TWINE_WHEEL_URL)

    repo_a = python_repo_factory()
    repo_b = python_repo_factory()
    body = {"add_content_units": [content.pulp_href]}
    monitor_task(python_bindings.RepositoriesPythonApi.modify(repo_a.pulp_href, body).task)
    monitor_task(python_bindings.RepositoriesPythonApi.modify(repo_b.pulp_href, body).task)

    distro_a = python_distribution_factory(repository=repo_a)
    distro_b = python_distribution_factory(repository=repo_b)

    # Yank in repo A only
    response = python_bindings.PypiYankApi.yank(
        path=distro_a.base_path, yank={"name": TWINE_NAME, "version": TWINE_VERSION}
    )
    monitor_task(response.task)

    # Repo A should have a yank marker, repo B should not
    summary_a = python_content_summary(repository=repo_a, version=2)
    assert summary_a.present["python.python_yank"]["count"] == 1
    summary_b = python_content_summary(repository=repo_b, version=1)
    assert "python.python_yank" not in summary_b.present

    # Yank in repo B too, then unyank only in repo A
    response = python_bindings.PypiYankApi.yank(
        path=distro_b.base_path, yank={"name": TWINE_NAME, "version": TWINE_VERSION}
    )
    monitor_task(response.task)

    response = python_bindings.PypiUnyankApi.unyank(
        path=distro_a.base_path, yank={"name": TWINE_NAME, "version": TWINE_VERSION}
    )
    monitor_task(response.task)

    # Repo A should be not-yanked, repo B should remain yanked
    summary_a = python_content_summary(repository=repo_a, version=3)
    assert "python.python_yank" not in summary_a.present
    summary_b = python_content_summary(repository=repo_b, version=2)
    assert summary_b.present["python.python_yank"]["count"] == 1


@pytest.mark.parallel
def test_yank_nonexistent_package(
    python_bindings, python_repo_factory, python_distribution_factory
):
    """
    Yanking a package not in the repo should return 404.
    """
    repo = python_repo_factory()
    distro = python_distribution_factory(repository=repo)

    with pytest.raises(python_bindings.ApiException) as exc:
        python_bindings.PypiYankApi.yank(
            path=distro.base_path, yank={"name": "nonexistent-package", "version": "99.99.99"}
        )
    assert exc.value.status == 404


@pytest.mark.parallel
def test_yank_no_repository(python_bindings, python_distribution_factory):
    """
    Yanking on a distribution with no repository should return 400.
    """
    distro = python_distribution_factory()

    with pytest.raises(python_bindings.ApiException) as exc:
        python_bindings.PypiYankApi.yank(
            path=distro.base_path, yank={"name": TWINE_NAME, "version": TWINE_VERSION}
        )
    assert exc.value.status == 400
