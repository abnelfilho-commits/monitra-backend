from sqlalchemy.orm import Session

from app.core.constants import StatusSessao
from app.models.sessao_assistencial import SessaoAssistencial

from app.services.registros_longitudinais import (
    criar_registro_longitudinal,
    obter_registro_longitudinal,
)

class RegistroLongitudinalService:
    """
    Integra uma Sessão Assistencial ao fluxo existente
    de Registros Longitudinais.
    """

    @staticmethod
    def criar_a_partir_da_sessao(
        db: Session,
        sessao: SessaoAssistencial,
        payload,
    ):
        if sessao.status not in {
            StatusSessao.EM_ANDAMENTO,
            StatusSessao.REALIZADA,
        }:
            raise ValueError(
                "Somente sessões em andamento ou realizadas "
                "podem gerar um Registro Longitudinal."
            )

        if sessao.registro_longitudinal_id is not None:
            raise ValueError(
                "Esta sessão já possui um Registro Longitudinal."
            )

        if payload.paciente_id != sessao.paciente_id:
            raise ValueError(
                "O paciente do registro não corresponde "
                "ao paciente da sessão."
            )

        try:
            registro = criar_registro_longitudinal(
                db=db,
                payload=payload,
            )

            sessao.registro_longitudinal_id = registro.id

            db.commit()
            db.refresh(sessao)

            # Retorna o formato completo esperado pelo schema,
            # incluindo o dicionário de respostas.
            return obter_registro_longitudinal(
                db=db,
                registro_id=registro.id,
            )

        except Exception:
            db.rollback()
            raise