import argparse
import json
import pathlib
from aero.concurrency_mutator import generate_concurrency_mutants
from aero.grammar_mutator import generate_grammar_mutants
from aero.icfg import build_icfg
from aero.llvm_ir_mutator import check_llvm_tooling, emit_llvm_ir, mutate_llvm_ir


def run_analysis(target_path: str, output_path: str | None = None):
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
    else:
        report["note"] = f"extensao '{suffix}' sem analisador especifico"

    if output_path:
        out_file = pathlib.Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return report


def main():
    parser = argparse.ArgumentParser(description="Executa análise estática e mutação no Aero.")
    parser.add_argument("target", nargs="?", default="examples/demo/calc.py", help="Ficheiro alvo (.py, .ll, .c, .cpp)")
    parser.add_argument("-o", "--output", help="Caminho opcional para salvar o relatório JSON")
    args = parser.parse_args()
    result = run_analysis(args.target, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
