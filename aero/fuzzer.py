"""Aero-AST-Mutation-Fuzzer: motor de mutacao de AST (Python).

Uso: python aero/fuzzer.py <pasta_do_projeto> <arquivo_alvo.py> "<comando de teste>"
         [-j N] [-o results.json] [--report report.md]
"""
import argparse, ast, difflib, json, os, pathlib, shutil, subprocess, sys
import tempfile, textwrap, time
from concurrent.futures import ThreadPoolExecutor

OPS = ["CMP_FLIP", "CONST_OFF_BY_ONE", "BOOL_SWAP", "LOCK_REMOVE", "JOIN_REMOVE"]
CONCURRENCY = {"LOCK_REMOVE", "JOIN_REMOVE"}
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

    def visit_Expr(self, n):  # remove thread.join() -> corrida com o fim da thread
        self.generic_visit(n)
        v = n.value
        if (self.op == "JOIN_REMOVE" and isinstance(v, ast.Call)
                and isinstance(v.func, ast.Attribute) and v.func.attr == "join"
                and not v.args and self._hit(n)):
            return ast.copy_location(ast.Pass(), n)
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


def _eval(job, project, target, test_cmd, code, orig):
    op, k = job
    m = Mutator(op, k)
    tree = ast.fix_missing_locations(m.visit(ast.parse(code)))
    mut_src = ast.unparse(tree)
    before, after = diff_lines(orig, mut_src.splitlines())
    with tempfile.TemporaryDirectory() as d:
        work = pathlib.Path(d) / "p"
        shutil.copytree(project, work)
        (work / target).write_text(mut_src, encoding="utf-8")
        t0 = time.time()
        try:
            r = subprocess.run(test_cmd, shell=True, cwd=work,
                               capture_output=True, timeout=30)
            killed = r.returncode != 0
        except subprocess.TimeoutExpired:
            killed = True  # timeout = comportamento alterado
    return {"op": op, "line": m.line, "fn": m.fn, "before": before, "after": after,
            "status": "killed" if killed else "survived",
            "ms": int((time.time() - t0) * 1000)}


def ranking(mutants):
    """Risco por funcao: quem tem mais mutantes sobreviventes vem primeiro."""
    by = {}
    for m in mutants:
        a = by.setdefault(m["fn"], [0, 0])
        a[0] += 1
        a[1] += m["status"] == "survived"
    rows = [{"fn": f, "total": t, "survived": s, "rate": round(s / t, 3)}
            for f, (t, s) in by.items()]
    return sorted(rows, key=lambda r: (-r["survived"], -r["rate"], r["fn"]))


def make_report(data):
    ms = data["mutants"]
    surv = [m for m in ms if m["status"] == "survived"]
    score = 100 * (1 - len(surv) / max(1, len(ms)))
    out = [f"# Relatório de mutação: `{data['target']}`", "",
           f"**Mutation score: {score:.1f}%** ({len(ms) - len(surv)} detectados, "
           f"{len(surv)} sobreviveram, {len(ms)} no total)", "",
           "## Ranking de risco por função", "",
           "| Função | Mutantes | Sobreviveram | Taxa |", "|---|---:|---:|---:|"]
    out += [f"| `{r['fn']}` | {r['total']} | {r['survived']} | {100 * r['rate']:.0f}% |"
            for r in data["risk"]]
    out += ["", "## Mutantes que sobreviveram", ""]
    for m in surv[:15]:
        flag = " ⚠️ concorrência" if m["op"] in CONCURRENCY else ""
        out += [f"**#{m['id']} `{m['op']}`** em `{m['fn']}` (linha {m['line']}){flag}", "",
                "```diff", *("- " + x for x in m["before"].splitlines()),
                *("+ " + x for x in m["after"].splitlines()), "```", ""]
    if len(surv) > 15:
        out.append(f"_...e mais {len(surv) - 15} mutantes._")
    return "\n".join(out) + "\n"


def run(project, target, test_cmd, out="results.json", jobs=None, report=None):
    t0, project = time.time(), pathlib.Path(project)
    code = (project / target).read_text(encoding="utf-8")
    orig = ast.unparse(ast.parse(code)).splitlines()
    todo = [(op, k) for op in OPS for k in range(count_sites(code, op))]
    jobs = jobs or os.cpu_count() or 4
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        res = list(pool.map(lambda j: _eval(j, project, target, test_cmd, code, orig), todo))
    mutants = [{"id": i, **r} for i, r in enumerate(res, 1)]
    data = {"target": target, "edges": call_graph(ast.parse(code)),
            "risk": ranking(mutants), "mutants": mutants}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if report:
        pathlib.Path(report).write_text(make_report(data), encoding="utf-8")
    surv = sum(m["status"] == "survived" for m in mutants)
    print(f"{len(mutants)} mutantes | {surv} sobreviveram | score "
          f"{100 * (1 - surv / max(1, len(mutants))):.1f}% | {jobs} workers | "
          f"{time.time() - t0:.1f}s")
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mutation testing por AST (Python).")
    ap.add_argument("project", help="pasta do projeto")
    ap.add_argument("target", help="arquivo alvo, relativo à pasta do projeto")
    ap.add_argument("test_cmd", help="comando que roda os testes")
    ap.add_argument("-j", "--jobs", type=int, help="mutantes em paralelo (padrão: nº de CPUs)")
    ap.add_argument("-o", "--out", default="results.json")
    ap.add_argument("--report", help="gera um relatório em Markdown neste caminho")
    a = ap.parse_args(argv)
    run(a.project, a.target, a.test_cmd, a.out, a.jobs, a.report)


if __name__ == "__main__":
    main()
