import ast


BOOLEAN_VARIANTS = [
    lambda a, b: ast.BoolOp(op=ast.And(), values=[a, b]),
    lambda a, b: ast.BoolOp(op=ast.Or(), values=[a, b]),
    lambda a, b: ast.UnaryOp(op=ast.Not(), operand=ast.BoolOp(op=ast.And(), values=[a, b])),
    lambda a, b: ast.UnaryOp(op=ast.Not(), operand=ast.BoolOp(op=ast.Or(), values=[a, b])),
]

CMP_OPS = [ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq]


class GrammarMutator(ast.NodeTransformer):
    """Gera mutantes guiados por regras gramaticais em expressões booleanas e comparações."""

    def __init__(self, rule_index: int):
        self.rule_index = rule_index
        self.current_site = 0
        self.line = 0

    def _match(self, node) -> bool:
        hit = self.current_site == self.rule_index
        self.current_site += 1
        if hit:
            self.line = getattr(node, "lineno", self.line)
        return hit

    def visit_BoolOp(self, node: ast.BoolOp):
        self.generic_visit(node)
        if len(node.values) >= 2 and self._match(node):
            builder = BOOLEAN_VARIANTS[self.rule_index % len(BOOLEAN_VARIANTS)]
            return ast.copy_location(builder(node.values[0], node.values[1]), node)
        return node

    def visit_Compare(self, node: ast.Compare):
        self.generic_visit(node)
        if node.ops and self._match(node):
            current_op_cls = type(node.ops[0])
            candidates = [cls for cls in CMP_OPS if cls is not current_op_cls]
            chosen_cls = candidates[self.rule_index % len(candidates)]
            node.ops[0] = chosen_cls()
        return node


def count_grammar_sites(code: str) -> int:
    tree = ast.parse(code)
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and len(node.values) >= 2:
            total += 1
        elif isinstance(node, ast.Compare) and node.ops:
            total += 1
    return total


def generate_grammar_mutants(code: str):
    total = count_grammar_sites(code)
    mutants = []
    for idx in range(total):
        mutator = GrammarMutator(idx)
        tree = ast.fix_missing_locations(mutator.visit(ast.parse(code)))
        mutants.append({
            "grammar_id": idx + 1,
            "line": mutator.line,
            "code": ast.unparse(tree),
        })
    return mutants
