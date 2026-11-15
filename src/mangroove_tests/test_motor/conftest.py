from pytest import fixture

from mangroove_motor.analisis import Resultado, analizar
from mangroove_motor.perfil import Perfil
from mangroove_motor.sintetica import Escena, generar

########################################################################################

SEMILLA: int = 12345

########################################################################################


@fixture(scope="session")
def escena() -> Escena:
    return generar()


@fixture(scope="session")
def resultado(escena: Escena) -> Resultado:
    return analizar(
        pila=escena.pila,
        auxiliares=escena.auxiliares,
        grilla=escena.grilla,
        perfil=Perfil(),
        semilla=SEMILLA,
    )
