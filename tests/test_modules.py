import json
from aero.concurrency_mutator import generate_concurrency_mutants
from aero.grammar_mutator import count_grammar_sites, generate_grammar_mutants
from aero.icfg import build_icfg
from aero.llvm_ir_mutator import check_llvm_tooling, mutate_llvm_ir
from aero.risk_report import build_risk_ranking, render_markdown_report


def test_grammar_mutator():
    code = "def f(a, b):\n    if a > b and b != 0:\n        return a\n    return b\n"
    assert count_grammar_sites(code) >= 2
    mutants = generate_grammar_mutants(code)
    assert len(mutants) >= 2


def test_icfg_interprocedural():
    code = "def helper(x):\n    return x + 1\n\ndef main(v):\n    if v > 0:\n        return helper(v)\n    return 0\n"
    graph = build_icfg(code)
    assert len(graph["nodes"]) > 0
    assert any(e["type"] == "call" for e in graph["edges"])


def test_concurrency_mutator():
    code = "import threading\nlock = threading.Lock()\ndef run():\n    with lock:\n        pass\n    lock.release()\n"
    mutants = generate_concurrency_mutants(code)
    assert len(mutants) == 2


def test_llvm_ir_mutator():
    info = check_llvm_tooling()
    assert "clang" in info and "llvmlite" in info
    ir = "define i32 @f(i32 %a, i32 %b) {\nentry:\n  %r = add i32 %a, %b\n  ret i32 %r\n}\n"
    mutants = mutate_llvm_ir(ir)
    assert len(mutants) == 1
    assert mutants[0]["kind"] == "ir_add_to_sub"


def test_risk_report(tmp_path):
    target_file = tmp_path / "sample.py"
    target_file.write_text("def alpha(x):\n    return x + 1\n", encoding="utf-8")
    results_file = tmp_path / "results.json"
    results_file.write_text(
        json.dumps({
            "target": "sample.py",
            "mutants": [{"id": 1, "op": "AOR", "line": 2, "status": "survived"}],
        }),
        encoding="utf-8",
    )
    target, ranking = build_risk_ranking(tmp_path, results_file)
    assert target == "sample.py"
    assert ranking[0]["function"] == "alpha"
    md = render_markdown_report(target, ranking)
    assert "Mutation Risk Report" in md
