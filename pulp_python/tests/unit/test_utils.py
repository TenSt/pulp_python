from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from pulp_python.app.utils import build_content_url


@override_settings(
    CONTENT_ORIGIN="http://pulp.example.com",
    CONTENT_PATH_PREFIX="/pulp/content/",
    PYPI_API_HOSTNAME="http://unused.example.com",
)
class TestBuildContentUrl(SimpleTestCase):
    def test_url_without_domain(self):
        url = build_content_url("my-pypi/", "twine-5.1.0-py3-none-any.whl")
        self.assertEqual(
            url,
            "http://pulp.example.com/pulp/content/my-pypi/twine-5.1.0-py3-none-any.whl",
        )

    def test_url_with_domain(self):
        domain = SimpleNamespace(name="default")
        url = build_content_url("my-pypi", "pkg.whl", domain=domain)
        self.assertEqual(
            url,
            "http://pulp.example.com/pulp/content/default/my-pypi/pkg.whl",
        )


@override_settings(
    CONTENT_ORIGIN="",
    CONTENT_PATH_PREFIX="/pulp/content/",
    PYPI_API_HOSTNAME="https://pypi.example.com",
)
class TestBuildContentUrlFallbackOrigin(SimpleTestCase):
    def test_falls_back_to_pypi_api_hostname(self):
        url = build_content_url("foo", "bar.whl")
        self.assertEqual(url, "https://pypi.example.com/pulp/content/foo/bar.whl")
