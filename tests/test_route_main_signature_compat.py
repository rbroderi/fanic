import ast
from pathlib import Path


def _route_files() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    sites_dir = root / "src" / "fanic" / "cylinder_sites"
    return sorted(path for path in sites_dir.rglob("*.ex.*.py") if path.is_file())


def _main_param_names(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            names: set[str] = set()
            for arg in node.args.posonlyargs:
                names.add(arg.arg)
            for arg in node.args.args:
                names.add(arg.arg)
            for arg in node.args.kwonlyargs:
                names.add(arg.arg)
            return names
    return set()


def test_route_main_functions_do_not_define_named_deps_parameter() -> None:
    offenders: list[str] = []
    for route_file in _route_files():
        tree = ast.parse(route_file.read_text(encoding="utf-8"), filename=str(route_file))
        param_names = _main_param_names(tree)
        if "deps" in param_names:
            offenders.append(str(route_file))

    assert offenders == [], (
        "Route main() functions must not define a named deps parameter because "
        "Cylinder injects args by name and raises KeyError when deps is absent. "
        "Use **kwargs and read kwargs.get('deps') for test-only injection. Offenders: " + ", ".join(offenders)
    )
