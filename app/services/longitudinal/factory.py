from app.services.longitudinal.adapters.registro import RegistroAdapter
from app.services.longitudinal.adapters.intervencao import IntervencaoAdapter
from app.services.longitudinal.adapters.mchat import MChatAdapter
from app.services.longitudinal.adapters.denver import DenverAdapter


ADAPTERS = {
    "REGISTRO": RegistroAdapter(),
    "INTERVENCAO": IntervencaoAdapter(),
    "MCHAT": MChatAdapter(),
    "DENVER": DenverAdapter(),
}


def get_adapter(tipo: str):
    adapter = ADAPTERS.get(tipo.upper())

    if adapter is None:
        raise ValueError(f"Tipo de evento '{tipo}' não suportado.")

    return adapter