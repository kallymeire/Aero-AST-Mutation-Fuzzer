import json
import pathlib
import sys
from aero.concurrency_mutator import generate_concurrency_mutants
from aero.grammar_mutator import generate_grammar_mutants
from aero.icfg import build_icfg
from aero.llvm_ir_mutator import check_llvm_tooling, emit_llvm_ir, mutate_llvm_ir


def run_analysis(target_path: str):
    path = pathlib.Path(target_path)
    content = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    report = {
        "target": str(path),
        "llvm_tooling": check_llvm_tooling(),
    }

    if suffix == ".py":
        icfg = build_icfg(content)
        grammar_muts = generate_grammar_mutants(content)
        conc_muts = generate_concurrency_mutants(content)
        report.update({
            "icfg_nodes": len(icfg["nodes"]),
            "icfg_edges": len(icfg["edges"]),
            "grammar_mutants": len(grammar_muts),
            "concurrency_mutants": len(conc_muts),
        })
    elif suffix == ".ll":
        ir_muts = mutate_llvm_ir(content)
        report["llvm_ir_mutants"] = len(ir_muts)
    elif suffix in {".c", ".cc", ".cpp", ".cxx"}:
        if report["llvm_tooling"]["clang"]:
            ir_text = emit_llvm_ir(str(path))
            report["llvm_ir_mutants"] = len(mutate_llvm_ir(ir_text))
        else:
            report["llvm_ir_mutants"] = 0
            report["note"] = "clang indisponivel no ambiente; emissao de IR ignorada"

    return report


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "examples/demo/calc.py"
    print(json.dumps(run_analysis(target), indent=2, ensure_ascii=False))
