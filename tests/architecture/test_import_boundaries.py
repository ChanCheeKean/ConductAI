import ast


def test_provider_and_framework_imports_stay_in_adapters(project_root):
    violations = []
    for path in (project_root / "src/conductai").rglob("*.py"):
        relative = path.relative_to(project_root / "src/conductai").as_posix()
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.startswith("openai") and not relative.startswith("adapters/models/"):
                    violations.append((relative, name))
                if name.startswith(("langgraph", "langchain", "deepagents")) and not relative.startswith("adapters/runtime/"):
                    violations.append((relative, name))
    assert not violations


def test_domain_imports_only_stdlib_and_pydantic(project_root):
    violations = []
    for path in (project_root / "src/conductai/domain").rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.level:
                    continue
                root = node.module.split(".")[0]
                if root not in {"__future__", "datetime", "enum", "typing", "pydantic"}:
                    violations.append((path.name, node.module))
    assert not violations
