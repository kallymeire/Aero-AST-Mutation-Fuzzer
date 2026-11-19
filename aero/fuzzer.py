"""Aero-AST-Mutation-Fuzzer: nucleo de mutacao de AST (Python).

Uso: python fuzzer.py <pasta_do_projeto> <arquivo_alvo.py> "<comando de teste>"
Gera results.json, que o dashboard le diretamente.
"""
import ast, difflib, json, pathlib, shutil, subprocess, sys, tempfile, textwrap, time

OPS = ["CMP_FLIP", "CONST_OFF_BY_ONE", "BOOL_SWAP", "LOCK_REMOVE"]
CMP_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE,
            ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}


class Mutator(ast.NodeTransformer):
    """Aplica o operador `op` apenas no k-esimo ponto elegivel da AST."""

    def __init__(self, op, target):
        self.op, self.target, self.i, self.line = op, target, -1, 0
        self.fn, self.stack = "<module>", []

    def _hit(self, node):
        self.i += 1
        if self.i == self.target:
            self.line = getattr(node, "lineno", 0)
            self.fn = self.stack[-1] if self.stack else "<module>"
            return True
        return False

    def visit_FunctionDef(self, n):
        self.stack.append(n.name)
        self.generic_visit(n)
        self.stack.pop()
        return n

    def visit_Compare(self, n):
        self.generic_visit(n)
        if self.op == "CMP_FLIP" and self._hit(n):
            n.ops = [CMP_SWAP.get(type(o), type(o))() for o in n.ops]
        return n

    def visit_Constant(self, n):
        if (self.op == "CONST_OFF_BY_ONE" and isinstance(n.value, int)
                and not isinstance(n.value, bool) and self._hit(n)):
            n.value += 1
        return n

    def visit_BoolOp(self, n):
        self.generic_visit(n)
        if self.op == "BOOL_SWAP" and self._hit(n):
            n.op = ast.Or() if isinstance(n.op, ast.And) else ast.And()
        return n

    def visit_With(self, n):  # remove a secao critica -> candidato a data race
        self.generic_visit(n)
        if (self.op == "LOCK_REMOVE"
                and "lock" in ast.unparse(n.items[0].context_expr).lower()
                and self._hit(n)):
            return n.body
        return n


def call_graph(tree):
    """Grafo de chamadas entre funcoes definidas no proprio arquivo."""
    fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    names, edges = {f.name for f in fns}, set()
    for f in fns:
        for c in ast.walk(f):
            if (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                    and c.func.id in names and c.func.id != f.name):
                edges.add((f.name, c.func.id))
    return sorted(edges)


def count_sites(src, op):
    m = Mutator(op, 10**9)
    m.visit(ast.parse(src))
    return m.i + 1


def diff_lines(a, b):
    """Primeiro trecho que mudou entre o codigo original e o mutado."""
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            return (textwrap.dedent("\n".join(a[i1:i2][:4])),
                    textwrap.dedent("\n".join(b[j1:j2][:4])))
    return "", ""


import concurrent.futures
import os

def _eval_mutant(args):
    mutant_id, project, target, test_cmd, op, k, code = args
    m = Mutator(op, k)
    tree = ast.fix_missing_locations(m.visit(ast.parse(code)))
    with tempfile.TemporaryDirectory() as d:
        work = pathlib.Path(d) / 'p'
        shutil.copytree(project, work)
        (work / target).write_text(ast.unparse(tree), encoding='utf-8')
        t0 = time.time()
        try:
            r = subprocess.run(test_cmd, shell=True, cwd=work, capture_output=True, timeout=30)
            killed = r.returncode != 0
        except subprocess.TimeoutExpired:
            killed = True
        return {'id': mutant_id, 'op': op, 'line': getattr(m, 'line', 0), 'status': 'killed' if killed else 'survived', 'ms': int((time.time() - t0) * 1000)}

def run(project, target, test_cmd, out='results.json', workers=None):
    code = (pathlib.Path(project) / target).read_text(encoding='utf-8')
    tasks = []
    mid = 1
    for op in OPS:
        for k in range(count_sites(code, op)):
            tasks.append((mid, project, target, test_cmd, op, k, code))
            mid += 1
    max_workers = workers or os.cpu_count() or 4
    mutants = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as ex:
        for res in ex.map(_eval_mutant, tasks):
            mutants.append(res)
    mutants.sort(key=lambda x: x['id'])
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'target': target, 'mutants': mutants}, f, indent=2)
    surv = sum(x['status'] == 'survived' for x in mutants)
    score = 100 * (1 - surv / max(1, len(mutants)))
    print(f'{len(mutants)} mutantes | {surv} sobreviveram | score {score:.1f}% (workers={max_workers})')

if __name__ == '__main__':
    run(*sys.argv[1:4])
