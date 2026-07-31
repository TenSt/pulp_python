import pytest

from pulp_python.tests.functional.constants import PYTHON_SM_PROJECT_SPECIFIER


@pytest.mark.parallel
def test_version_specifier_filter(python_bindings, python_repo_with_sync, python_remote_factory):
    """Test filtering content by PEP 440 version specifier."""
    remote = python_remote_factory(includes=PYTHON_SM_PROJECT_SPECIFIER)
    repo = python_repo_with_sync(remote=remote)

    result = python_bindings.ContentPackagesApi.list(
        repository_version=repo.latest_version_href,
        name="Django",
        version_specifier=">=1.10.2,<1.10.4",
    )
    versions = {c.version for c in result.results}
    assert "1.10.2" in versions
    assert "1.10.3" in versions
    assert "1.10.4" not in versions


@pytest.mark.parallel
def test_version_specifier_filter_invalid(python_bindings):
    """Test that an invalid specifier returns a 400 error."""
    with pytest.raises(python_bindings.ApiException) as exc:
        python_bindings.ContentPackagesApi.list(version_specifier=">=invalid!version")
    assert exc.value.status == 400
