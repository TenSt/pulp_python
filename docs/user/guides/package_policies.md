# Package Policies

Python repositories offer two mechanisms for controlling which packages they accept:
**blocklists** to prevent specific packages from being added, and
**package substitution control** to prevent silent replacement of existing packages.

By default, when either policy rejects a package, the entire repository version operation fails.
Set `error_on_reject` to `False` to instead skip rejected packages and continue adding the rest.

## Setup

If you do not already have a repository, create one:

```bash
pulp python repository create --name foo
```

## Package Blocklist

A repository can have a blocklist that prevents specific packages from being added.
Blocklist entries can match by package `name` (blocks all versions), package `name` with an exact `version`, or exact `filename`.
Exactly one of `name` or `filename` must be provided.

Package `name` is normalized using [PEP 503](https://peps.python.org/pep-0503/) before being stored, 
and `version` must follow [PEP 440](https://peps.python.org/pep-0440/) rules.

Each entry records the PRN of the user who created it in the `added_by` field.

### Add a blocklist entry

=== "By name"

    ```bash
    # Block all versions of shelf-reader
    pulp python repository blocklist add --repository "foo" --name "shelf-reader"
    ```

=== "By name and version"

    ```bash
    # Block only shelf-reader 0.1
    pulp python repository blocklist add --repository "foo" --name "shelf-reader" --version "0.1"
    ```

=== "By filename"

    ```bash
    # Block only shelf-reader-0.1.tar.gz
    pulp python repository blocklist add --repository "foo" --filename "shelf-reader-0.1.tar.gz"
    ```

### List blocklist entries

```bash
pulp python repository blocklist list --repository "foo"
```

### Show a blocklist entry

=== "By name"

    ```bash
    pulp python repository blocklist show --repository "foo" --name "shelf-reader"
    ```

=== "By name and version"

    ```bash
    pulp python repository blocklist show --repository "foo" --name "shelf-reader" --version "0.1"
    ```

=== "By filename"

    ```bash
    pulp python repository blocklist show --repository "foo" --filename "shelf-reader-0.1.tar.gz"
    ```

### Remove a blocklist entry

=== "By name"

    ```bash
    pulp python repository blocklist remove --repository "foo" --name "shelf-reader"
    ```

=== "By name and version"

    ```bash
    pulp python repository blocklist remove --repository "foo" --name "shelf-reader" --version "0.1"
    ```

=== "By filename"

    ```bash
    pulp python repository blocklist remove --repository "foo" --filename "shelf-reader-0.1.tar.gz"
    ```

Once an entry is removed, packages matching it can be added to the repository again.

## Package Yanking

[PEP 592](https://peps.python.org/pep-0592/) allows marking package versions as "yanked".
Package installers like `pip` will skip yanked versions when resolving dependencies.
However, if a user requests an exact version (e.g. `pip install twine==5.1.0`),
the yanked package will still be installed, with a warning.

Yank status is per-repository: yanking a package in one repository does not affect other repositories
that contain the same package.

### Yank a package version

To yank a package version, send a POST request to the distribution's `/yank/` endpoint:

```bash
http POST http://localhost:5001/pypi/default/<distribution-base-path>/yank/ \
    name=shelf-reader version=0.1 yanked_reason="critical security bug" \
    -a admin:password
```

The `yanked_reason` field is optional. If omitted, the package is marked as yanked with no reason.

Yanking creates a new repository version with the yank marker added.
Yanking a version that is already yanked with the same reason is a no-op (no new repository version is created).
Re-yanking with a different reason will update the reason and create a new repository version.

### Unyank a package version

```bash
http POST http://localhost:5001/pypi/default/<distribution-base-path>/unyank/ \
    name=shelf-reader version=0.1 \
    -a admin:password
```

Unyanking creates a new repository version with the yank marker removed.
Unyanking a version that is not yanked is a no-op.

### Syncing yanked packages

When syncing from a remote that has yanked packages (e.g. PyPI), the yank status is preserved automatically.
Pulp creates a yank marker for each yanked version and includes it in the repository version.

### Viewing yank status

Yank status is visible in the Simple API and the PyPI Metadata API.

Yank markers can also be listed via the REST API:

```bash
# List all yank markers
http GET http://localhost:5001/pulp/default/api/v3/content/python/yanks/ -a admin:password

# List yank markers for a specific repository version
http GET http://localhost:5001/pulp/default/api/v3/content/python/yanks/?repository_version=<repo-version-href> -a admin:password
```

## Package Substitution

By default, Python repositories allow package substitution: uploading, syncing, or adding a package
with the same filename as an existing package but a different checksum will silently replace it.

This behavior is controlled by the `allow_package_substitution` field on a Python repository.
When set to `False`, any operation (upload, sync, or modify) that would replace an existing package with a different checksum is rejected.
Re-adding a package with the same filename *and* the same checksum is always accepted (idempotent).

### Disable package substitution

```bash
pulp python repository update --repository "foo" --block-package-substitution
```

You can also set this when creating a repository:

```bash
pulp python repository create --name "foo2" --block-package-substitution
```

### Re-enable package substitution

```bash
pulp python repository update --repository "foo" --allow-package-substitution
```

Once re-enabled, packages with duplicate filenames can replace existing content again.

## Partial rejection (`error_on_reject`)

When a package is rejected by the blocklist or by the package substitution policy
(`allow_package_substitution=False`), the default behavior (`error_on_reject=True`) is to fail
the entire operation. No packages from the request are added.

Setting `error_on_reject` to `False` changes this: rejected packages are skipped, remaining
packages are added, and skipped packages are recorded in a task progress report (including
filenames and package pks).

### Disable failing on rejected packages

```bash
http PATCH http://localhost:5001/pulp/api/v3/repositories/python/python/<repo_pk>/ \
  error_on_reject:=false -a admin:password
```

You can also set this when creating a repository:

```bash
http POST http://localhost:5001/pulp/api/v3/repositories/python/python/ \
  name=foo3 error_on_reject:=false allow_package_substitution:=false -a admin:password
```

### Re-enable failing on rejected packages

```bash
http PATCH http://localhost:5001/pulp/api/v3/repositories/python/python/<repo_pk>/ \
  error_on_reject:=true -a admin:password
```
