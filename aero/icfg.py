"""ICFG simplificado: CFG por funcao (blocos, ramos, lacos) + arestas de chamada."""
import ast
import pathlib

_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _calls(node):
    """Funcoes chamadas por nome simples, f(...), dentro de uma expressao."""
    if node is None:
        return []
    return [c.func.id for c in ast.walk(node)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)]


def build_icfg(code: str):
    """Retorna {"nodes": [...], "edges": [...]}.

    Arestas: "cfg" (fluxo), "back" (volta de laco) e "call" (chamada -> entrada
    da funcao chamada). Nao modela excecoes, chamadas indiretas nem retornos.
    """
    tree = ast.parse(code)
    funcs = [n for n in ast.walk(tree) if isinstance(n, _FUNCS)]
    nodes, edges, entries, by_id = [], [], {}, {}

    def add(kind, fn, line, end, calls=(), lock=False):
        n = {"id": f"N{len(nodes) + 1}", "kind": kind, "label": "", "function": fn,
             "line": line, "end_line": end, "calls": list(calls), "lock": lock}
        nodes.append(n)
        by_id[n["id"]] = n
        return n["id"]

    def link(frontier, nid, etype="cfg"):
        edges.extend({"from": p, "to": nid, "type": etype} for p in frontier)

    for f in funcs:
        fn, exits = f.name, []
        entry = add("entry", fn, f.lineno, f.lineno)
        entries.setdefault(fn, entry)

        def simple(line, end, calls, frontier, lock):
            blk = by_id[frontier[0]] if len(frontier) == 1 else None
            if blk and blk["kind"] == "block" and blk["lock"] == lock:
                blk["end_line"] = end          # funde instrucoes seguidas no mesmo bloco
                blk["calls"] += calls
                return frontier
            n = add("block", fn, line, end, calls, lock)
            link(frontier, n)
            return [n]

        def seq(stmts, frontier, lock=False):
            for s in stmts:
                frontier = one(s, frontier, lock)
            return frontier

        def one(s, frontier, lock):
            if isinstance(s, _FUNCS + (ast.ClassDef,)):
                return frontier                # funcoes aninhadas tem o proprio CFG
            end = getattr(s, "end_lineno", s.lineno)
            if isinstance(s, ast.If):
                n = add("branch", fn, s.lineno, s.test.end_lineno, _calls(s.test), lock)
                link(frontier, n)
                then = seq(s.body, [n], lock)
                other = seq(s.orelse, [n], lock) if s.orelse else [n]
                return list(dict.fromkeys(then + other))
            if isinstance(s, (ast.For, ast.AsyncFor, ast.While)):
                head = s.test if isinstance(s, ast.While) else s.iter
                n = add("loop", fn, s.lineno, head.end_lineno, _calls(head), lock)
                link(frontier, n)
                link(seq(s.body, [n], lock), n, "back")
                return [n]
            if isinstance(s, ast.Return):
                n = add("return", fn, s.lineno, end, _calls(s.value), lock)
                link(frontier, n)
                exits.append(n)
                return []
            if isinstance(s, (ast.With, ast.AsyncWith)):
                lk = lock or any("lock" in ast.unparse(i.context_expr).lower() for i in s.items)
                head_calls = sum((_calls(i.context_expr) for i in s.items), [])
                return seq(s.body, simple(s.lineno, s.lineno, head_calls, frontier, lk), lk)
            if isinstance(s, ast.Try):
                out = seq(s.body, frontier, lock)
                for h in s.handlers:
                    out = out + seq(h.body, frontier, lock)
                return seq(s.finalbody, seq(s.orelse, out, lock), lock)
            return simple(s.lineno, end, _calls(s), frontier, lock)

        tail = seq(f.body, [entry])
        ex = add("exit", fn, f.end_lineno, f.end_lineno)
        link(tail + exits, ex)

    for n in nodes:                            # chamadas: resolve depois de ler tudo
        for callee in dict.fromkeys(n["calls"]):
            if callee in entries and n["kind"] != "entry":
                edges.append({"from": n["id"], "to": entries[callee], "type": "call"})
        span = f"L{n['line']}" + (f"-{n['end_line']}" if n["end_line"] != n["line"] else "")
        c = ", ".join(dict.fromkeys(n["calls"]))
        n["label"] = {"entry": f"enter {n['function']}", "exit": f"exit {n['function']}",
                      "branch": f"if @ {span}", "loop": f"loop @ {span}",
                      "return": f"return @ {span}"}.get(
            n["kind"], f"call {c} @ {span}" if c else f"block @ {span}")
        if n["lock"]:
            n["label"] += " [lock]"
    return {"nodes": nodes, "edges": edges}


def locate(graph, fn, line):
    """Id do no do ICFG que contem `line` dentro da funcao `fn` (ou o mais proximo)."""
    cand = [n for n in graph["nodes"] if n["function"] == fn and n["kind"] not in ("entry", "exit")]
    inside = [n for n in cand if n["line"] <= line <= n["end_line"]]
    if inside:
        return min(inside, key=lambda n: n["end_line"] - n["line"])["id"]
    before = [n for n in cand if n["line"] <= line]
    if before:
        return max(before, key=lambda n: n["line"])["id"]
    return next((n["id"] for n in graph["nodes"]
                 if n["function"] == fn and n["kind"] == "entry"), None)


if __name__ == "__main__":
    import json
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "examples/demo/calc.py"
    g = build_icfg(pathlib.Path(target).read_text(encoding="utf-8"))
    print(json.dumps({"node_count": len(g["nodes"]), "edge_count": len(g["edges"]),
                      "edges": g["edges"]}, indent=2, ensure_ascii=False))
