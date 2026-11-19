import ast
import pathlib


def build_icfg(code: str):
    """Constrói um ICFG simplificado (nós intraprocedurais + arestas interprocedurais de chamada)."""
    tree = ast.parse(code)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    nodes = []
    edges = []
    node_counter = 0

    def add_node(kind: str, label: str, func_name: str, line: int) -> str:
        nonlocal node_counter
        node_counter += 1
        node_id = f"N{node_counter}"
        nodes.append({
            "id": node_id,
            "kind": kind,
            "label": label,
            "function": func_name,
            "line": line,
        })
        return node_id

    for func_name, func_node in functions.items():
        entry_id = add_node("entry", f"enter {func_name}", func_name, getattr(func_node, "lineno", 0))
        prev_id = entry_id

        for stmt in ast.walk(func_node):
            if stmt is func_node:
                continue
            line = getattr(stmt, "lineno", 0)
            if isinstance(stmt, ast.If):
                nid = add_node("branch", f"if @ L{line}", func_name, line)
                edges.append({"from": prev_id, "to": nid, "type": "cfg"})
                prev_id = nid
            elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
                nid = add_node("loop", f"loop @ L{line}", func_name, line)
                edges.append({"from": prev_id, "to": nid, "type": "cfg"})
                prev_id = nid
            elif isinstance(stmt, ast.Return):
                nid = add_node("return", f"return @ L{line}", func_name, line)
                edges.append({"from": prev_id, "to": nid, "type": "cfg"})
                prev_id = nid
            elif isinstance(stmt, ast.Call):
                callee = None
                if isinstance(stmt.func, ast.Name):
                    callee = stmt.func.id
                elif isinstance(stmt.func, ast.Attribute):
                    callee = stmt.func.attr
                nid = add_node("call", f"call {callee or '?'} @ L{line}", func_name, line)
                edges.append({"from": prev_id, "to": nid, "type": "cfg"})
                prev_id = nid
                if callee and callee in functions:
                    target_entry = next(
                        (n["id"] for n in nodes if n["function"] == callee and n["kind"] == "entry"),
                        None,
                    )
                    if target_entry:
                        edges.append({"from": nid, "to": target_entry, "type": "call"})

        exit_id = add_node("exit", f"exit {func_name}", func_name, getattr(func_node, "end_lineno", getattr(func_node, "lineno", 0)))
        edges.append({"from": prev_id, "to": exit_id, "type": "cfg"})

    return {"nodes": nodes, "edges": edges}


if __name__ == "__main__":
    import json
    import sys

    target_file = sys.argv[1] if len(sys.argv) > 1 else "examples/demo/calc.py"
    graph = build_icfg(pathlib.Path(target_file).read_text(encoding="utf-8"))
    print(json.dumps({"node_count": len(graph["nodes"]), "edge_count": len(graph["edges"]), "edges": graph["edges"]}, indent=2, ensure_ascii=False))
