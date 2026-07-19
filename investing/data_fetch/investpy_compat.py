from __future__ import annotations

import importlib
import sys
import warnings
from importlib import resources
from types import ModuleType
from typing import Any


def _resource_package_name(package: Any) -> str:
    return package if isinstance(package, str) else str(package.__name__)


def _legacy_resource_filename(package: Any, resource_name: str) -> str:
    return str(resources.files(_resource_package_name(package)).joinpath(resource_name))


def _legacy_resource_exists(package: Any, resource_name: str) -> bool:
    target = resources.files(_resource_package_name(package)).joinpath(resource_name)
    return target.is_file() or target.is_dir()


def _import_investpy() -> Any:
    # investpy 1.0.8 imports setuptools' deprecated pkg_resources module.
    # Suppress only that dependency warning while preserving all other warnings.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"pkg_resources is deprecated as an API.*",
            category=UserWarning,
        )
        return importlib.import_module("investpy")


def load_investpy() -> Any:
    """Import investpy when modern setuptools no longer ships pkg_resources."""
    try:
        return _import_investpy()
    except ModuleNotFoundError as exc:
        if exc.name != "pkg_resources":
            raise

    # investpy 1.0.8 only uses these two resource helpers. Keep the shim local
    # to its import so unrelated packages never see a partial pkg_resources API.
    shim = ModuleType("pkg_resources")
    shim.resource_filename = _legacy_resource_filename  # type: ignore[attr-defined]
    shim.resource_exists = _legacy_resource_exists  # type: ignore[attr-defined]
    for module_name in list(sys.modules):
        if module_name == "investpy" or module_name.startswith("investpy."):
            sys.modules.pop(module_name, None)
    sys.modules["pkg_resources"] = shim
    try:
        return _import_investpy()
    finally:
        sys.modules.pop("pkg_resources", None)
