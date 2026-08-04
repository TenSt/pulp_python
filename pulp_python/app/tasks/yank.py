from packaging.utils import canonicalize_name

from pulpcore.plugin.exceptions import ValidationError
from pulpcore.plugin.tasking import aadd_and_remove

from pulp_python.app.models import PackageYank, PythonPackageContent, PythonRepository


async def ayank_package(repository_pk, name, version, yanked_reason=""):
    """
    Yank a package version in a repository by adding a PackageYank marker.
    Creates a new repository version with the yank marker added.
    """
    normalized = canonicalize_name(name)
    repository = await PythonRepository.objects.aget(pk=repository_pk)
    latest = await repository.alatest_version()

    exists = await PythonPackageContent.objects.filter(
        pk__in=latest.content, name_normalized=normalized, version=version
    ).aexists()
    if not exists:
        raise ValidationError(f"Package {name}=={version} not found in repository")

    existing_yank = await PackageYank.objects.filter(
        pk__in=latest.content, name_normalized=normalized, version=version
    ).afirst()
    if existing_yank and existing_yank.yanked_reason == yanked_reason:
        return

    yank_marker, _ = await PackageYank.objects.aget_or_create(
        name_normalized=normalized,
        version=version,
        yanked_reason=yanked_reason,
        _pulp_domain_id=repository.pulp_domain_id,
    )

    await aadd_and_remove(
        repository_pk=repository.pk,
        add_content_units=[yank_marker.pk],
        remove_content_units=[],
    )


async def aunyank_package(repository_pk, name, version):
    """
    Unyank a package version in a repository by removing its PackageYank marker.
    Creates a new repository version with the yank marker removed.
    """
    normalized = canonicalize_name(name)
    repository = await PythonRepository.objects.aget(pk=repository_pk)
    latest = await repository.alatest_version()

    yank_marker = await PackageYank.objects.filter(
        pk__in=latest.content, name_normalized=normalized, version=version
    ).afirst()

    if yank_marker is None:
        return

    await aadd_and_remove(
        repository_pk=repository.pk,
        add_content_units=[],
        remove_content_units=[yank_marker.pk],
    )
