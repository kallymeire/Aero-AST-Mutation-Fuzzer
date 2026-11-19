import ast, pathlib, sys
from aero.fuzzer import Mutator, count_sites, call_graph, run, ranking


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


def test_join_remove():
    src = "def f(t):\n    t.join()\n    return ','.join(['a'])\n"
    assert count_sites(src, "JOIN_REMOVE") == 1
    m = Mutator("JOIN_REMOVE", 0)
    out = ast.unparse(ast.fix_missing_locations(m.visit(ast.parse(src))))
    assert "t.join()" not in out and "','.join" in out


def test_ranking_ordena_por_sobreviventes():
    ms = [{"fn": "a", "status": "killed"}, {"fn": "b", "status": "survived"},
          {"fn": "b", "status": "survived"}]
    assert ranking(ms)[0]["fn"] == "b"


def test_paralelo_igual_ao_serial(tmp_path):
    demo = pathlib.Path(__file__).parent.parent / "examples" / "demo"
    cmd = f'"{sys.executable}" test_calc.py'
    a = run(demo, "calc.py", cmd, str(tmp_path / "a.json"), jobs=1)
    b = run(demo, "calc.py", cmd, str(tmp_path / "b.json"), jobs=4)
    assert [m["status"] for m in a["mutants"]] == [m["status"] for m in b["mutants"]]
