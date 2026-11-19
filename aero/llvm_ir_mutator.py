import importlib.util
import pathlib
import re
import shutil
import subprocess
import tempfile


def check_llvm_tooling():
    """Verifica disponibilidade de clang e llvmlite no ambiente."""
    clang_path = shutil.which("clang")
    has_llvmlite = importlib.util.find_spec("llvmlite") is not None
    return {
        "clang": clang_path,
        "llvmlite": has_llvmlite,
        "ready": bool(clang_path),
    }


def emit_llvm_ir(source_path: str) -> str:
    """Compila um arquivo C/C++ para LLVM IR (.ll) usando clang -S -emit-llvm."""
    clang_path = shutil.which("clang")
    if not clang_path:
        raise RuntimeError("Compilador 'clang' não encontrado no PATH.")

    src = pathlib.Path(source_path)
    with tempfile.TemporaryDirectory() as tmpdir:
        ll_out = pathlib.Path(tmpdir) / f"{src.stem}.ll"
        proc = subprocess.run(
            [clang_path, "-S", "-emit-llvm", str(src), "-o", str(ll_out)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Falha ao emitir LLVM IR: {proc.stderr.strip()}")
        return ll_out.read_text(encoding="utf-8")


def validate_ir_with_llvmlite(ir_text: str) -> bool:
    """Valida sintaxe/módulo do LLVM IR com llvmlite quando disponível."""
    if importlib.util.find_spec("llvmlite") is None:
        return False
    import llvmlite.binding as llvm

    llvm.initialize()
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    mod = llvm.parse_assembly(ir_text)
    mod.verify()
    return True


def mutate_llvm_ir(ir_text: str):
    """Gera variantes mutadas simples de instruções aritméticas e icmp no LLVM IR."""
    lines = ir_text.splitlines()
    mutants = []
    mid = 0

    swaps = [
        (re.compile(r"\badd\b"), "sub", "ir_add_to_sub"),
        (re.compile(r"\bsub\b"), "add", "ir_sub_to_add"),
        (re.compile(r"\bicmp\s+slt\b"), "icmp sgt", "ir_icmp_slt_to_sgt"),
        (re.compile(r"\bicmp\s+sgt\b"), "icmp slt", "ir_icmp_sgt_to_slt"),
        (re.compile(r"\bicmp\s+eq\b"), "icmp ne", "ir_icmp_eq_to_ne"),
        (re.compile(r"\bicmp\s+ne\b"), "icmp eq", "ir_icmp_ne_to_eq"),
    ]

    for idx, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if stripped.startswith((";", "!", "target ", "source_filename", "attributes", "define ", "declare ")):
            continue
        for pattern, replacement, kind in swaps:
            if pattern.search(line):
                mid += 1
                new_lines = lines.copy()
                new_lines[idx - 1] = pattern.sub(replacement, line, count=1)
                mutants.append({
                    "id": mid,
                    "kind": kind,
                    "line": idx,
                    "ir": "\n".join(new_lines),
                })
                break

    return mutants


if __name__ == "__main__":
    import json
    import sys

    info = check_llvm_tooling()
    if len(sys.argv) > 1:
        ir = emit_llvm_ir(sys.argv[1])
        muts = mutate_llvm_ir(ir)
        print(json.dumps({"tooling": info, "mutants_count": len(muts)}, indent=2))
    else:
        sample_ir = """define i32 @add_vals(i32 %a, i32 %b) {
entry:
  %sum = add nsw i32 %a, %b
  %cmp = icmp slt i32 %sum, 10
  ret i32 %sum
}
"""
        muts = mutate_llvm_ir(sample_ir)
        print(json.dumps({
            "tooling": info,
            "mutants_count": len(muts),
            "mutants": [{"id": m["id"], "kind": m["kind"], "line": m["line"]} for m in muts],
        }, indent=2))
