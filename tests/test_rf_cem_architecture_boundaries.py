"""No-CST dependency guards for the R0B RF-CEM architecture layers."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_cst

ROOT = Path(__file__).resolve().parents[1]
RF_CEM = ROOT / "src" / "rf_cem"


def test_r0b_architecture_packages_are_importable() -> None:
    for name in ("semantic", "representation", "compiler", "observation", "workbench"):
        module = importlib.import_module(f"rf_cem.{name}")
        assert module is not None


@pytest.mark.parametrize(
    ("package", "forbidden_roots"),
    [
        (
            "semantic",
            {
                "cadquery",
                "OCP",
                "cst",
                "rf_cem.compiler",
                "rf_cem.parametric_geometry",
                "rf_cem.representation",
            },
        ),
        (
            "representation",
            {
                "cst",
                "rf_cem.compiler",
                "rf_cem.semantic",
            },
        ),
        (
            "observation",
            {
                "cadquery",
                "OCP",
                "cst",
                "rf_cem.parametric_geometry.reconstruction",
            },
        ),
    ],
)
def test_architecture_layer_has_no_forbidden_imports(
    package: str, forbidden_roots: set[str]
) -> None:
    imports = _package_imports(RF_CEM / package)
    violations = sorted(
        imported
        for imported in imports
        if any(
            imported == root or imported.startswith(root + ".")
            for root in forbidden_roots
        )
    )
    assert violations == []


def test_compiler_is_the_reserved_composition_layer() -> None:
    compiler = (RF_CEM / "compiler" / "__init__.py").read_text(encoding="utf-8")
    assert "only core layer allowed to combine" in compiler
    assert "Compile(T, {Ri(theta_i)})" in compiler


def _package_imports(package: Path) -> set[str]:
    imports: set[str] = set()
    for path in package.rglob("*.py"):
        module_parts = path.relative_to(ROOT / "src").with_suffix("").parts
        package_parts = module_parts[:-1]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    if node.module:
                        imports.add(node.module)
                    continue
                parent_count = node.level - 1
                if parent_count > len(package_parts):
                    imports.add("<invalid-relative-import>")
                    continue
                base = package_parts[: len(package_parts) - parent_count]
                if node.module:
                    imports.add(".".join((*base, *node.module.split("."))))
                else:
                    imports.update(
                        ".".join((*base, alias.name))
                        for alias in node.names
                        if alias.name != "*"
                    )
    return imports
