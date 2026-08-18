from typing import Any, List, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.agenda_cuidado import AgendaCuidado
from app.models.sessao_assistencial import SessaoAssistencial


class SchedulingService:
    """
    Responsável pela persistência das Sessões Assistenciais.

    O Service não calcula datas e não sugere cronogramas.
    Ele apenas confirma e grava um cronograma previamente revisado.
    """

    @staticmethod
    def confirmar_cronograma(
        db: Session,
        agenda: AgendaCuidado,
        cronograma: Sequence[Any],
    ) -> List[SessaoAssistencial]:
        if not cronograma:
            raise ValueError(
                "O cronograma deve possuir pelo menos uma sessão."
            )

        if not agenda.pts:
            raise ValueError(
                "O planejamento não está vinculado a um PTS válido."
            )

        paciente_id = getattr(
            agenda.pts,
            "paciente_id",
            None,
        )

        if paciente_id is None:
            raise ValueError(
                "Não foi possível identificar o paciente do planejamento."
            )

        sessoes_existentes = (
            db.query(SessaoAssistencial.id)
            .filter(
                SessaoAssistencial.agenda_cuidado_id
                == agenda.id
            )
            .first()
        )

        if sessoes_existentes:
            raise ValueError(
                "O cronograma deste planejamento já foi confirmado."
            )

        numeros_recebidos = [
            item.numero
            for item in cronograma
        ]

        if len(numeros_recebidos) != len(
            set(numeros_recebidos)
        ):
            raise ValueError(
                "O cronograma possui números de sessão duplicados."
            )

        numeros_esperados = list(
            range(1, len(cronograma) + 1)
        )

        if sorted(numeros_recebidos) != numeros_esperados:
            raise ValueError(
                "As sessões devem possuir numeração sequencial "
                "iniciando em 1."
            )

        sessoes = []

        try:
            for item in cronograma:
                sessao = SessaoAssistencial(
                    agenda_cuidado_id=agenda.id,
                    paciente_id=paciente_id,
                    profissional_id=(
                        agenda.profissional_id
                    ),
                    numero_sessao=item.numero,
                    data_agendada=item.data,
                    hora_inicio=getattr(
                        item,
                        "hora_inicio",
                        None,
                    ),
                    hora_fim=getattr(
                        item,
                        "hora_fim",
                        None,
                    ),
                    duracao_minutos=(
                        agenda.duracao_minutos
                    ),
                    status="AGENDADA",
                )

                db.add(sessao)
                sessoes.append(sessao)

            db.commit()

            for sessao in sessoes:
                db.refresh(sessao)

            return sessoes

        except IntegrityError as erro:
            db.rollback()

            raise ValueError(
                "Não foi possível confirmar o cronograma. "
                "Verifique se as sessões já foram cadastradas."
            ) from erro

        except Exception:
            db.rollback()
            raise