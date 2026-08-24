from datetime import datetime, timezone
from json import loads
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from pulp_python.app.models import PythonDistribution
from pulp_python.app.utils import PYPI_LAST_SERIAL, PYPI_SERIAL_CONSTANT, PYPI_SIMPLE_V1_JSON


def _json_body(response):
    body = response.body
    if isinstance(body, bytes):
        body = body.decode()
    return loads(body)


@override_settings(DOMAIN_ENABLED=False)
class TestContentHandlerJson(SimpleTestCase):
    def _distro(self, repo_version=None):
        distro = MagicMock()
        distro.base_path = "demo-python"
        distro.get_repository_publication_and_version.return_value = (
            MagicMock(),
            repo_version,
            None,
        )
        return distro

    def test_empty_path_returns_none(self):
        distro = self._distro()
        self.assertIsNone(PythonDistribution.content_handler_json(distro, ""))
        distro.get_repository_publication_and_version.assert_not_called()

    def test_no_repository_version_returns_none(self):
        distro = self._distro(repo_version=None)
        self.assertIsNone(PythonDistribution.content_handler_json(distro, "simple"))

    def test_unknown_path_returns_none(self):
        distro = self._distro(repo_version=MagicMock())
        with patch("pulp_python.app.models.PythonPackageContent.objects") as mock_objects:
            mock_objects.filter.return_value = MagicMock()
            self.assertIsNone(PythonDistribution.content_handler_json(distro, "not-a-pypi-path"))

    def test_pypi_json_suffix_returns_none(self):
        """``pypi/*/json`` stays on content_handler; content_handler_json must not claim it."""
        distro = self._distro(repo_version=MagicMock())
        with patch("pulp_python.app.models.PythonPackageContent.objects") as mock_objects:
            mock_objects.filter.return_value = MagicMock()
            self.assertIsNone(PythonDistribution.content_handler_json(distro, "pypi/twine/json"))

    def test_simple_extra_path_returns_none(self):
        distro = self._distro(repo_version=MagicMock())
        with patch("pulp_python.app.models.PythonPackageContent.objects") as mock_objects:
            mock_objects.filter.return_value = MagicMock()
            self.assertIsNone(PythonDistribution.content_handler_json(distro, "simple/twine/extra"))

    @patch("pulp_python.app.models.json_response")
    @patch("pulp_python.app.models.python_content_to_json")
    @patch("pulp_python.app.models.PackageYank.objects")
    @patch("pulp_python.app.models.PythonPackageContent.objects")
    def test_pypi_package_returns_json_response(
        self, mock_objects, mock_yank, mock_to_json, mock_json_response
    ):
        repo_version = MagicMock()
        distro = self._distro(repo_version=repo_version)
        package_qs = MagicMock()
        mock_objects.filter.return_value.filter.return_value = package_qs
        mock_yank.filter.return_value.values_list.return_value = []
        mock_to_json.return_value = {"info": {"name": "twine"}, "last_serial": 0}
        mock_json_response.return_value = "RESPONSE"

        result = PythonDistribution.content_handler_json(distro, "pypi/Twine")

        self.assertEqual(result, "RESPONSE")
        mock_objects.filter.return_value.filter.assert_called_with(name_normalized="twine")
        mock_to_json.assert_called_once()
        kwargs = mock_to_json.call_args.kwargs
        self.assertEqual(kwargs["version"], None)
        self.assertIs(kwargs["repository_version"], repo_version)
        mock_json_response.assert_called_once()
        headers = mock_json_response.call_args.kwargs["headers"]
        self.assertEqual(headers[PYPI_LAST_SERIAL], str(PYPI_SERIAL_CONSTANT))

    @patch("pulp_python.app.models.json_response")
    @patch("pulp_python.app.models.python_content_to_json")
    @patch("pulp_python.app.models.PackageYank.objects")
    @patch("pulp_python.app.models.PythonPackageContent.objects")
    def test_pypi_version_passes_version(
        self, mock_objects, mock_yank, mock_to_json, mock_json_response
    ):
        distro = self._distro(repo_version=MagicMock())
        mock_objects.filter.return_value.filter.return_value = MagicMock()
        mock_yank.filter.return_value.values_list.return_value = []
        mock_to_json.return_value = {"info": {"name": "twine", "version": "5.1.0"}}
        mock_json_response.return_value = "RESPONSE"

        result = PythonDistribution.content_handler_json(distro, "pypi/twine/5.1.0")

        self.assertEqual(result, "RESPONSE")
        self.assertEqual(mock_to_json.call_args.kwargs["version"], "5.1.0")

    @patch("pulp_python.app.models.python_content_to_json")
    @patch("pulp_python.app.models.PackageYank.objects")
    @patch("pulp_python.app.models.PythonPackageContent.objects")
    def test_pypi_missing_package_returns_none(self, mock_objects, mock_yank, mock_to_json):
        distro = self._distro(repo_version=MagicMock())
        mock_objects.filter.return_value.filter.return_value = MagicMock()
        mock_yank.filter.return_value.values_list.return_value = []
        mock_to_json.return_value = None

        self.assertIsNone(PythonDistribution.content_handler_json(distro, "pypi/missing"))

    @patch("pulp_python.app.models.PythonPackageContent.objects")
    def test_simple_index_returns_pep691(self, mock_objects):
        distro = self._distro(repo_version=MagicMock())
        names_qs = MagicMock()
        names_qs.order_by.return_value.values_list.return_value.distinct.return_value = [
            "shelf-reader",
            "twine",
        ]
        mock_objects.filter.return_value = names_qs

        result = PythonDistribution.content_handler_json(distro, "simple")

        self.assertEqual(result.content_type, PYPI_SIMPLE_V1_JSON)
        body = _json_body(result)
        self.assertEqual(body["meta"]["api-version"], "1.1")
        self.assertEqual([p["name"] for p in body["projects"]], ["shelf-reader", "twine"])

    @patch("pulp_python.app.models.build_content_url", return_value="http://example/pkg.whl")
    @patch("pulp_python.app.models.PythonPackageContent.objects")
    def test_simple_detail_returns_pep691(self, mock_objects, mock_build_url):
        distro = self._distro(repo_version=MagicMock())
        pkg = MagicMock()
        pkg.filename = "twine-5.1.0-py3-none-any.whl"
        pkg.sha256 = "abc123"
        pkg.metadata_sha256 = "def456"
        pkg.requires_python = ">=3.8"
        pkg.size = 12
        pkg.repo_added_time = datetime(2026, 1, 2, tzinfo=timezone.utc)
        pkg.pulp_created = datetime(2026, 1, 1, tzinfo=timezone.utc)
        pkg.version = "5.1.0"

        packages = MagicMock()
        packages.exists.return_value = True
        packages.__iter__.return_value = iter([pkg])
        mock_objects.filter.return_value.filter.return_value.annotate.return_value = packages

        result = PythonDistribution.content_handler_json(distro, "simple/Twine")

        self.assertEqual(result.content_type, PYPI_SIMPLE_V1_JSON)
        body = _json_body(result)
        self.assertEqual(body["name"], "twine")
        self.assertEqual(body["versions"], ["5.1.0"])
        self.assertEqual(len(body["files"]), 1)
        self.assertEqual(body["files"][0]["filename"], pkg.filename)
        self.assertEqual(body["files"][0]["hashes"], {"sha256": "abc123"})
        self.assertEqual(body["files"][0]["url"], "http://example/pkg.whl")
        mock_build_url.assert_called_once()

    @patch("pulp_python.app.models.PythonPackageContent.objects")
    def test_simple_detail_missing_package_returns_none(self, mock_objects):
        distro = self._distro(repo_version=MagicMock())
        packages = MagicMock()
        packages.exists.return_value = False
        mock_objects.filter.return_value.filter.return_value.annotate.return_value = packages

        self.assertIsNone(PythonDistribution.content_handler_json(distro, "simple/missing"))
