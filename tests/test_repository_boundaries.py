"""Small guards for runtime boundaries and repository hygiene, without lint dependencies."""
import ast
import re
import subprocess
import sys
from pathlib import Path

import yaml
import httpx
import pytest


ROOT = Path(__file__).resolve().parents[1]


def _requirements(filename):
    names = set()
    for line in (ROOT / filename).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            names.update(_requirements(line[3:].strip()))
        else:
            names.add(re.split(r"[<>=!~\[;]", line, maxsplit=1)[0].lower())
    return names


def test_runtime_dependencies_are_separate_from_development_and_legacy_ui():
    runtime = _requirements("requirements-workbench.txt")
    assert {"fastapi", "uvicorn", "pymupdf", "openai"} <= runtime
    assert not {"streamlit", "pytest", "groq", "pyodbc"} & runtime
    assert {"pytest", "streamlit", "fastapi", "httpx"} <= _requirements("requirements-dev.txt")


def test_unit_tests_cannot_open_external_http_connections():
    transport = httpx.HTTPTransport()
    with pytest.raises(AssertionError, match="External HTTP is disabled"):
        transport.handle_request(httpx.Request("GET", "https://example.invalid/"))
    transport.close()


def test_workbench_imports_without_streamlit_or_groq_sdk():
    script = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'streamlit', 'groq', 'pytest', 'pyodbc'}:
        raise ImportError('Optional dependency unexpectedly required: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from src.analyzer.workbench_service import WorkbenchService
from src.workbench_api import create_app
"""
    result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_streamlit_helpers_are_reachable_from_its_entrypoint():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}

    def references(node):
        return {child.id for child in ast.walk(node)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)}

    roots = set().union(*(references(node) for node in tree.body if not isinstance(node, ast.FunctionDef)))
    pending = list(roots & functions.keys())
    reachable = set(pending)
    while pending:
        for name in references(functions[pending.pop()]) & functions.keys() - reachable:
            reachable.add(name)
            pending.append(name)
    assert not functions.keys() - reachable


def test_runtime_modules_do_not_import_removed_experiments():
    forbidden = {"agent", "agent_runner", "db", "tools", "groq"}
    paths = [ROOT / "app.py", ROOT / "notifier.py", *sorted((ROOT / "src").rglob("*.py"))]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            assert not forbidden & {module.split(".")[0] for module in modules}, path


def test_readme_relative_document_links_exist():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)]+)\)", text)
    local = [target.split("#", 1)[0] for target in targets if "://" not in target and not target.startswith("#")]
    assert local
    assert all((ROOT / target).is_file() for target in local)


def test_ci_actions_use_explicit_commit_references():
    workflow = yaml.safe_load((ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8"))
    references = [step["uses"] for job in workflow["jobs"].values()
                  for step in job["steps"] if "uses" in step]
    assert references
    assert all(re.fullmatch(r"actions/[\w-]+@[a-f0-9]{40}", reference) for reference in references)
