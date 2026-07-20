from datetime import timedelta
from math import floor

from app.services.scheduling_models import (
    PlanejamentoAssistencial,
    SessaoGerada,
)


class SchedulingEngine:
    """
    Transforma um Planejamento Assistencial
    em um Cronograma Assistencial Proposto.

    Não grava dados no banco.
    """

    @staticmethod
    def generate_sessions(
        planejamento: PlanejamentoAssistencial,
    ) -> list[SessaoGerada]:

        if planejamento.quantidade_sessoes <= 0:
            raise ValueError(
                "Quantidade de sessões deve ser maior que zero."
            )

        if planejamento.frequencia_semanal <= 0:
            raise ValueError(
                "Frequência semanal deve ser maior que zero."
            )

        if planejamento.duracao_minutos <= 0:
            raise ValueError(
                "Duração da sessão deve ser maior que zero."
            )

        intervalo = (
            7 / planejamento.frequencia_semanal
        )

        sessoes = []
        acumulado = 0.0

        for numero in range(
            1,
            planejamento.quantidade_sessoes + 1,
        ):
            if numero == 1:
                data_agendada = planejamento.data_inicio
            else:
                acumulado += intervalo

                data_agendada = (
                    planejamento.data_inicio
                    + timedelta(
                        days=floor(acumulado)
                    )
                )

            sessoes.append(
                SessaoGerada(
                    numero=numero,
                    data_agendada=data_agendada,
                    duracao_minutos=(
                        planejamento.duracao_minutos
                    ),
                )
            )

        return sessoes