import ast
from aero.fuzzer import Mutator, count_sites, call_graph


def test_cmp_flip_registra_funcao():
    m = Mutator("CMP_FLIP", 0)
    tree = ast.fix_missing_locations(m.visit(ast.parse("def f(x):\n    return x < 3\n")))
    assert "x <= 3" in ast.unparse(tree) and m.fn == "f"


def test_conta_pontos():
    assert count_sites("a = 1\nb = 2\n", "CONST_OFF_BY_ONE") == 2


def test_lock_remove():
    src = "def f():\n    with lock:\n        x = 1\n"
    m = Mutator("LOCK_REMOVE", 0)
    assert "with" not in ast.unparse(ast.fix_missing_locations(m.visit(ast.parse(src))))


def test_grafo_de_chamadas():
    assert call_graph(ast.parse("def a():\n    b()\ndef b():\n    pass\n")) == [("a", "b")]
