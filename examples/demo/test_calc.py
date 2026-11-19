# Testes razoáveis, mas incompletos DE PROPÓSITO: assim alguns mutantes
# sobrevivem e o dashboard mostra onde a cobertura é frágil.
import calc
from calc import validate, clamp, add, process, main


def test_validate():
    assert validate(5)
    assert not validate(-1)


def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(15, 0, 10) == 10


def test_add():
    calc.total = 0
    assert add(2) == 2
    assert add(3) == 5


def test_process():
    calc.total = 0
    assert process([1, 2]) == 3


def test_main():
    calc.total = 0
    assert main() == (20, 4.5)


if __name__ == "__main__":
    test_validate(); test_clamp(); test_add(); test_process(); test_main()
