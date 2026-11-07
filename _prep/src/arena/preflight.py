"""Conservative static checks; the official runner remains the authority."""
import ast
import json
from pathlib import Path


def check_submission(path, contract_path):
    path = Path(path)
    contract = json.loads(Path(contract_path).read_text())
    if not isinstance(contract, dict):
        raise ValueError("contract must be a JSON object")
    required = {"entrypoint", "parameters", "allowed_imports", "max_bytes", "official_verified"}
    if required - contract.keys():
        raise ValueError("contract missing keys: " + ", ".join(sorted(required - contract.keys())))
    if type(contract["official_verified"]) is not bool:
        raise ValueError("official_verified must be boolean")
    if (not isinstance(contract["entrypoint"], str) or not contract["entrypoint"].isidentifier()
            or not isinstance(contract["parameters"], list)
            or any(not isinstance(name, str) or not name.isidentifier() for name in contract["parameters"])
            or not isinstance(contract["allowed_imports"], list)
            or any(not isinstance(name, str) for name in contract["allowed_imports"])
            or type(contract["max_bytes"]) is not int or contract["max_bytes"] < 1):
        raise ValueError("invalid contract signature, imports, or size limit")
    errors = []
    if path.suffix != ".py" or not path.is_file():
        raise ValueError("submission must be a regular .py file")
    if path.stat().st_size > contract["max_bytes"]:
        errors.append("file exceeds configured size limit")
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("file exceeds static inspection limit of 10 MB")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        # Parsing builds an AST even for context-invalid statements such as
        # top-level `break` or `return`. Compile checks them without execution.
        compile(tree, path.name, "exec")
    except SyntaxError as exc:
        return {"status": "failed", "errors": [f"syntax error at line {exc.lineno}: {exc.msg}"],
                "official_verified": contract["official_verified"], "submission_ready": False}
    entrypoints = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == contract["entrypoint"]]
    if len(entrypoints) != 1:
        errors.append("require exactly one top-level synchronous entrypoint function")
    else:
        args = entrypoints[0].args
        names = [arg.arg for arg in args.posonlyargs + args.args]
        if (names != contract["parameters"] or args.vararg or args.kwarg or args.kwonlyargs
                or args.defaults or args.kw_defaults):
            errors.append("entrypoint signature differs from configured positional parameters")
    allowed = set(contract["allowed_imports"])
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                errors.append("relative imports are not self-contained")
            imports.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "compile", "__import__"}:
                errors.append("dynamic code/import call requires manual review: " + node.func.id)
    for name in sorted(imports - allowed):
        errors.append("import not permitted by configured contract: " + name)
    return {"status": "failed" if errors else "static_checks_passed", "errors": errors,
            "official_verified": contract["official_verified"], "imports": sorted(imports),
            "submission_ready": False,
            "remaining": ["Run official samples and hidden-like edge cases in the official runner",
                          "Check runtime, memory, output, class-based interfaces and behavior manually",
                          "Static checks do not prove absence of network, secrets, filesystem access or side effects"]}
