import ast
import pathlib


RESOURCE_RELEASE_CALLS = {"close", "release", "free", "unlock"}


class ConcurrencyMemoryMutator(ast.NodeTransformer):
    """Aplica mutações focadas em concorrência (locks/with) e liberação de recursos/memória."""

    def __init__(self, site_index: int):
        self.site_index = site_index
        self.current_site = 0
        self.line = 0
        self.mutation_kind = ""

    def _hit(self, node, kind: str) -> bool:
        matched = self.current_site == self.site_index
        self.current_site += 1
        if matched:
            self.line = getattr(node, "lineno", self.line)
            self.mutation_kind = kind
        return matched

    def visit_With(self, node: ast.With):
        self.generic_visit(node)
        ctx_text = " ".join(ast.unparse(item.context_expr).lower() for item in node.items)
        if any(k in ctx_text for k in ("lock", "mutex", "sem", "thread", "file", "open")):
            if self._hit(node, "unwrap_with_context"):
                return node.body
        return node

    def visit_Expr(self, node: ast.Expr):
        self.generic_visit(node)
        if isinstance(node.value, ast.Call):
            fn = node.value.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            if name.lower() in RESOURCE_RELEASE_CALLS and self._hit(node, f"drop_{name.lower()}_call"):
                return ast.copy_location(ast.Pass(), node)
        return node


def generate_concurrency_mutants(code: str):
    tree = ast.parse(code)
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            ctx_text = " ".join(ast.unparse(item.context_expr).lower() for item in node.items)
            if any(k in ctx_text for k in ("lock", "mutex", "sem", "thread", "file", "open")):
                total += 1
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            fn = node.value.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            if name.lower() in RESOURCE_RELEASE_CALLS:
                total += 1

    mutants = []
    for idx in range(total):
        mutator = ConcurrencyMemoryMutator(idx)
        mutated_tree = ast.fix_missing_locations(mutator.visit(ast.parse(code)))
        mutants.append({
            "id": idx + 1,
            "kind": mutator.mutation_kind,
            "line": mutator.line,
            "code": ast.unparse(mutated_tree),
        })
    return mutants


if __name__ == "__main__":
    import json
    import sys

    sample = "import threading\nlock = threading.Lock()\ndef work():\n    with lock:\n        x = 1\n    lock.release()\n"
    src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else sample
    res = generate_concurrency_mutants(src)
    print(json.dumps({"count": len(res), "mutants": [{"id": m["id"], "kind": m["kind"], "line": m["line"]} for m in res]}, indent=2))
