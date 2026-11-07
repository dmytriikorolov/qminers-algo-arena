"""Conservative local screen for our files; not the server's static validator."""

import argparse
import ast
from pathlib import Path


ALLOWED_IMPORTS = {
    'math': {'ceil', 'exp', 'floor', 'sqrt'},
    'simulator.models': {
        'OrderBookSnapshot', 'OrderRequest', 'OrderStatus', 'OrderType',
        'PrivateOrderEvent', 'Side', 'Trade',
    },
    'simulator.strategy': {'BaseStrategy'},
}
BANNED_NAMES = {
    'open', 'eval', 'exec', 'compile', '__import__', 'getattr', 'setattr',
    'delattr', 'hasattr', 'type', 'globals', 'locals', 'vars', 'dir',
    'input', 'breakpoint', 'help', 'memoryview',
}


def check(path):
    source = path.read_bytes()
    errors = []
    if len(source) > 1024 * 1024:
        errors.append('File exceeds 1 MiB')
    tree = ast.parse(source, filename=str(path))
    strategies = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            errors.append(f'line {node.lineno}: use explicit allowed from-imports')
        elif isinstance(node, ast.ImportFrom):
            allowed = ALLOWED_IMPORTS.get(node.module, set())
            if node.level or any(alias.name not in allowed or alias.asname for alias in node.names):
                errors.append(f'line {node.lineno}: import outside local allowlist')
        elif isinstance(node, ast.Name) and (node.id in BANNED_NAMES or node.id.startswith('__')):
            errors.append(f'line {node.lineno}: banned name {node.id}')
        elif isinstance(node, ast.Attribute):
            if node.attr == 'format' or (node.attr.startswith('__') and node.attr != '__init__'):
                errors.append(f'line {node.lineno}: banned attribute {node.attr}')
        elif isinstance(node, ast.ClassDef):
            if any(isinstance(base, ast.Name) and base.id == 'BaseStrategy' for base in node.bases):
                strategies.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith('__') and node.name != '__init__':
                errors.append(f'line {node.lineno}: unexpected special method')
            if node.name == '__init__' and (len(node.args.args) != 1 or node.args.vararg or node.args.kwarg or node.args.kwonlyargs):
                errors.append(f'line {node.lineno}: constructor must take only self')
    if len(strategies) != 1:
        errors.append('Expected exactly one direct BaseStrategy subclass')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.files:
        errors = check(path)
        print(path, ':', '; '.join(errors) if errors else 'local screen passed')
        failed |= bool(errors)
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
