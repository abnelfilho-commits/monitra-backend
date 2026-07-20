from dataclasses import dataclass
from datetime import date


@dataclass
class PlanejamentoAssistencial:
    """
    DTO de entrada do Scheduling Engine.
    """

    data_inicio: date
    quantidade_sessoes: int
    frequencia_semanal: int
    duracao_minutos: int

    @classmethod
    def from_model(cls, agenda):
        if agenda.data_inicio is None:
            raise ValueError(
                "Data de início não informada."
            )

        if agenda.quantidade_sessoes is None:
            raise ValueError(
                "Quantidade de sessões não informada."
            )

        if agenda.frequencia_semanal is None:
            raise ValueError(
                "Frequência semanal não informada."
            )

        if agenda.duracao_minutos is None:
            raise ValueError(
                "Duração da sessão não informada."
            )

        return cls(
            data_inicio=agenda.data_inicio,
            quantidade_sessoes=agenda.quantidade_sessoes,
            frequencia_semanal=agenda.frequencia_semanal,
            duracao_minutos=agenda.duracao_minutos,
        )

    @property
    def intervalo_medio(self) -> float:
        return 7 / self.frequencia_semanal


@dataclass
class SessaoGerada:
    """
    Representa uma sessão sugerida pelo Scheduling Engine.
    Ainda não é uma sessão persistida no banco.
    """

    numero: int
    data_agendada: date
    duracao_minutos: int