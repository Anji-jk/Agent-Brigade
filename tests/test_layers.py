"""Each package may import only the packages below it (or its own).

    1  core      settings, database, trackers, locks, files
    2  pipeline  the orchestrator: runs agents, checks, merges
    3  backend   FastAPI routes and the use cases they call

A wrong import fails here instead of slowly tangling the code. Imports under
``if TYPE_CHECKING:`` are not dependencies at run time and are not counted.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PACKAGE_LAYERS = {"core": 1, "pipeline": 2, "backend": 3}


def layer_of(module: str) -> int | None:
    return PACKAGE_LAYERS.get(module.split(".")[0])


def module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def runtime_imports(tree: ast.AST) -> list[str]:
    found: list[str] = []

    def visit(node: ast.AST, type_checking: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.If) and "TYPE_CHECKING" in ast.unparse(child.test):
                visit(child, True)
                continue
            if not type_checking:
                if isinstance(child, ast.ImportFrom) and child.module and child.level == 0:
                    found.append(child.module)
                    found.extend(f"{child.module}.{alias.name}" for alias in child.names)
                elif isinstance(child, ast.Import):
                    found.extend(alias.name for alias in child.names)
            visit(child, type_checking)

    visit(tree, False)
    return found


def source_files() -> list[Path]:
    return sorted(p for name in PACKAGE_LAYERS for p in (ROOT / name).rglob("*.py"))


def violations() -> list[str]:
    bad = set()
    for path in source_files():
        module = module_name(path)
        mine = layer_of(module)
        for name in runtime_imports(ast.parse(path.read_text(encoding="utf-8"))):
            theirs = layer_of(name)
            if mine is not None and theirs is not None and theirs > mine:
                bad.add(f"{module} (layer {mine}) imports {name} (layer {theirs})")
    return sorted(bad)


def test_the_three_packages_exist():
    for name in PACKAGE_LAYERS:
        assert (ROOT / name / "__init__.py").is_file()


def test_no_module_imports_a_layer_above_it():
    assert violations() == []


def test_the_check_sees_runtime_imports_and_skips_type_checking_ones():
    tree = ast.parse(
        "from backend.api import stories\nif TYPE_CHECKING:\n    import backend.services.x\n"
    )
    assert runtime_imports(tree) == ["backend.api", "backend.api.stories"]
    assert layer_of("backend.api") > layer_of("pipeline.scheduler") > layer_of("core.settings")