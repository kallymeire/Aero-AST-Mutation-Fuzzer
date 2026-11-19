from aero.icfg import build_icfg, locate

SRC = '''
def helper(x):
    return x + 1


def f(x):
    if x > 0:
        y = helper(x)
    else:
        y = 0
    for i in range(3):
        y += i
    return y


def g():
    return later()


def later():
    return 1
'''


def _nodes(g):
    return {n["id"]: n for n in g["nodes"]}


def test_if_tem_dois_ramos():
    g = build_icfg(SRC)
    br = next(n for n in g["nodes"] if n["kind"] == "branch")
    assert len([e for e in g["edges"] if e["from"] == br["id"]]) == 2


def test_laco_tem_aresta_de_volta():
    assert any(e["type"] == "back" for e in build_icfg(SRC)["edges"])


def test_return_vai_direto_para_exit():
    g, ns = build_icfg(SRC), None
    ns = _nodes(g)
    ret = next(n for n in g["nodes"] if n["kind"] == "return" and n["function"] == "f")
    assert any(ns[e["to"]]["kind"] == "exit" for e in g["edges"] if e["from"] == ret["id"])


def test_chamada_para_funcao_definida_depois():
    g = build_icfg(SRC)
    ns = _nodes(g)
    assert any(e["type"] == "call" and ns[e["to"]]["function"] == "later" for e in g["edges"])


def test_chamada_de_metodo_nao_vira_aresta():
    src = "def add(n):\n    return n\n\n\ndef f(x):\n    return x.add(1)\n"
    assert not [e for e in build_icfg(src)["edges"] if e["type"] == "call"]


def test_locate_acha_o_no_pela_linha():
    g = build_icfg(SRC)
    assert _nodes(g)[locate(g, "f", 7)]["kind"] == "branch"
