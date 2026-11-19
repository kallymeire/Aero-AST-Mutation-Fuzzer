import ast
import json
import pathlib
import sys
from aero.fuzzer import call_graph


def _function_spans(code):
    tree = ast.parse(code)
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = getattr(node, "lineno", 0)
            end = getattr(node, "end_lineno", start)
            spans.append((node.name, start, end))
    spans.sort(key=lambda x: x[1])
    return spans


def build_risk_ranking(project, results_path="results.json", target_override=None):
    data = json.loads(pathlib.Path(results_path).read_text(encoding="utf-8"))
    target = target_override or data.get("target", "")
    code = (pathlib.Path(project) / target).read_text(encoding="utf-8")
    spans = _function_spans(code)
    cg = call_graph(ast.parse(code)); edges = cg[1] if isinstance(cg, tuple) and len(cg) > 1 and isinstance(cg[1], dict) else (cg if isinstance(cg, dict) else {})
    mutants = data.get("mutants", [])

    stats = {
        name: {
            "function": name,
            "total": 0,
            "survived": 0,
            "killed": 0,
            "callers_or_callees": len(edges.get(name, set())),
        }
        for name, _, _ in spans
    }
    stats["<module/outros>"] = {
        "function": "<module/outros>",
        "total": 0,
        "survived": 0,
        "killed": 0,
        "callers_or_callees": 0,
    }

    for m in mutants:
        line = m.get("line", 0)
        matched = next((name for name, start, end in spans if start <= line <= end), "<module/outros>")
        s = stats[matched]
        s["total"] += 1
        if m.get("status") == "survived":
            s["survived"] += 1
        else:
            s["killed"] += 1

    ranking = []
    for row in stats.values():
        if row["total"] == 0:
            continue
        surv_rate = row["survived"] / row["total"]
        risk_score = round((surv_rate * 80) + min(20, row["callers_or_callees"] * 5), 1)
        ranking.append({
            **row,
            "survival_rate": round(surv_rate * 100, 1),
            "risk_score": risk_score,
        })

    ranking.sort(key=lambda r: (-r["risk_score"], -r["survived"], r["function"]))
    return target, ranking


def render_markdown_report(target, ranking):
    lines = [
        f"## Mutation Risk Report — `{target}`",
        "",
        "| Rank | Função | Risco | Sobreviveram | Total | Taxa Sobrev. | Conexões Grafo |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    if not ranking:
        lines.append("| - | Sem mutantes registrados | 0.0 | 0 | 0 | 0.0% | 0 |")
    else:
        for idx, r in enumerate(ranking, 1):
            lines.append(
                f"| {idx} | `{r['function']}` | **{r['risk_score']}** | {r['survived']} | {r['total']} | {r['survival_rate']}% | {r['callers_or_callees']} |"
            )
    lines.extend(["", "> Gerado automaticamente para auditoria de testes e revisão de PR."])
    return "\n".join(lines)


def generate_report(project, results_path="results.json", out_md="risk_report.md"):
    target, ranking = build_risk_ranking(project, results_path)
    md = render_markdown_report(target, ranking)
    pathlib.Path(out_md).write_text(md, encoding="utf-8")
    return md


if __name__ == "__main__":
    proj = sys.argv[1]
    res = sys.argv[2] if len(sys.argv) > 2 else "results.json"
    out = sys.argv[3] if len(sys.argv) > 3 else "risk_report.md"
    print(generate_report(proj, res, out))
