"""Fast preflight for research scripts: syntax and third-party imported symbols.
Does not execute scripts or access the database.
"""
import ast
import importlib
from pathlib import Path
import py_compile
import sys

paths=sorted(Path("scripts").glob("audit_*.py"))
errors=[]
for path in paths:
    try:
        py_compile.compile(str(path),doraise=True)
        tree=ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node,ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith(("sklearn","scipy","numpy","pandas")):
                continue
            try:
                module=importlib.import_module(node.module)
                for alias in node.names:
                    if alias.name!="*" and not hasattr(module,alias.name):
                        errors.append(f"{path}:{node.lineno}: {node.module}.{alias.name} not found")
            except Exception as exc:
                errors.append(f"{path}:{node.lineno}: import {node.module}: {exc}")
    except Exception as exc:
        errors.append(f"{path}: {exc}")
print(f"Checked {len(paths)} research scripts")
if errors:
    print("\n".join(errors),file=sys.stderr)
    sys.exit(1)
print("All research syntax and supported dependency imports passed")
