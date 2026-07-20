from datetime import datetime

from sqlalchemy.orm import Session

from app.core.constants import StatusSessao
from app.models.modular import (
    CampoFormulario,
    FormularioModulo,
)
from app.models.pts import PTS
from app.models.sessao_assistencial import SessaoAssistencial
from app.schemas.registros_longitudinais import (
    CampoResposta,
    RegistroLongitudinalCreate,
)
from app.services.registro_longitudinal_service import (
    RegistroLongitudinalService,
)

class AssistentialExecutionService:
    
    @staticmethod
    def _resolver_contexto_registro(
        db: Session,
        sessao: SessaoAssistencial,
    ):
        agenda = sessao.agenda_cuidado

        if not agenda:
            raise ValueError(
                "A sessão não possui planejamento assistencial."
            )

        pts = (
            db.query(PTS)
            .filter(PTS.id == agenda.pts_id)
            .first()
        )

        if not pts:
            raise ValueError(
                "O PTS vinculado à sessão não foi encontrado."
            )

        if not pts.modulo_id:
            raise ValueError(
                "O PTS não possui módulo clínico definido."
            )

        formulario = (
            db.query(FormularioModulo)
            .filter(
                FormularioModulo.modulo_id == pts.modulo_id,
                FormularioModulo.codigo == "ATENDIMENTO_SESSAO",
                FormularioModulo.ativo.is_(True),
            )
            .first()
        )

        if not formulario:
            raise ValueError(
                "O formulário ATENDIMENTO_SESSAO não está "
                "configurado para o módulo clínico do PTS."
            )

        campo_narrativa = (
            db.query(CampoFormulario)
            .filter(
                CampoFormulario.formulario_id == formulario.id,
                CampoFormulario.nome_campo
                == "narrativa_atendimento",
                CampoFormulario.ativo.is_(True),
            )
            .first()
        )

        if not campo_narrativa:
            raise ValueError(
                "O campo narrativa_atendimento não está "
                "configurado no formulário da sessão."
            )

        campo_proximos_passos = (
            db.query(CampoFormulario)
            .filter(
                CampoFormulario.formulario_id == formulario.id,
                CampoFormulario.nome_campo == "proximos_passos",
                CampoFormulario.ativo.is_(True),
            )
            .first()
        )

        return {
            "modulo_id": pts.modulo_id,
            "formulario": formulario,
            "campo_narrativa": campo_narrativa,
            "campo_proximos_passos": campo_proximos_passos,
        }
        
    @staticmethod
    def confirmar(
        db: Session,
        sessao: SessaoAssistencial,
    ) -> SessaoAssistencial:
        if sessao.status != StatusSessao.AGENDADA:
            raise ValueError(
                "Somente sessões agendadas podem ser confirmadas."
            )

        sessao.status = StatusSessao.CONFIRMADA.value

        db.commit()
        db.refresh(sessao)

        return sessao

    @staticmethod
    def iniciar(
        db: Session,
        sessao: SessaoAssistencial,
    ) -> SessaoAssistencial:
        if sessao.status != StatusSessao.CONFIRMADA:
            raise ValueError(
                "Somente sessões confirmadas podem ser iniciadas."
            )

        agora = datetime.now()

        sessao.status = StatusSessao.EM_ANDAMENTO.value
        sessao.hora_inicio_real = agora.time()

        db.commit()
        db.refresh(sessao)

        return sessao

    @staticmethod
    def registrar_atendimento(
        db: Session,
        sessao: SessaoAssistencial,
        payload,
    ):
        if sessao.status != StatusSessao.EM_ANDAMENTO:
            raise ValueError(
                "Somente sessões em andamento podem registrar atendimento."
            )

        registro_payload = RegistroLongitudinalCreate(
            paciente_id=sessao.paciente_id,
            modulo_id=sessao.modulo_id,
            formulario_id=sessao.formulario_id,
            data_registro=datetime.now().date(),
            observacoes=payload.narrativa,
            respostas=[],
        )

        registro = RegistroLongitudinalService.criar_a_partir_da_sessao(
            db=db,
            sessao=sessao,
            payload=registro_payload,
        )

        return {
            "success": True,
            "sessao_id": sessao.id,
            "registro_id": registro.id,
            "mensagem": "Atendimento registrado com sucesso.",
        }

    @staticmethod
    def registrar_atendimento(
        db: Session,
        sessao: SessaoAssistencial,
        payload,
    ):
        if sessao.status != StatusSessao.EM_ANDAMENTO:
            raise ValueError(
                "Somente sessões em andamento podem "
                "registrar atendimento."
            )

        if not payload.narrativa.strip():
            raise ValueError(
                "Informe como foi o atendimento."
            )

        contexto = (
            AssistentialExecutionService
            ._resolver_contexto_registro(
                db=db,
                sessao=sessao,
            )
        )

        respostas = [
            CampoResposta(
                campo_id=contexto["campo_narrativa"].id,
                valor=payload.narrativa.strip(),
            )
        ]

        campo_proximos_passos = contexto[
            "campo_proximos_passos"
        ]

        if (
            campo_proximos_passos
            and payload.proximos_passos
        ):
            respostas.append(
                CampoResposta(
                    campo_id=campo_proximos_passos.id,
                    valor=payload.proximos_passos,
                )
            )

        registro_payload = RegistroLongitudinalCreate(
            paciente_id=sessao.paciente_id,
            modulo_id=contexto["modulo_id"],
            formulario_id=contexto["formulario"].id,
            data_registro=datetime.now().date(),
            origem="PROFISSIONAL",
            respostas=respostas,
        )

        registro = (
            RegistroLongitudinalService
            .criar_a_partir_da_sessao(
                db=db,
                sessao=sessao,
                payload=registro_payload,
            )
        )

        registro_id = (
            registro.get("id")
            if isinstance(registro, dict)
            else registro.id
        )

        return {
            "success": True,
            "sessao_id": sessao.id,
            "registro_id": registro_id,
            "mensagem": (
                "Atendimento registrado com sucesso."
            ),
        }

    @staticmethod
    def finalizar(
        db: Session,
        sessao: SessaoAssistencial,
    ) -> SessaoAssistencial:
        if sessao.status != StatusSessao.EM_ANDAMENTO:
            raise ValueError(
                "Somente sessões em andamento podem ser finalizadas."
            )

        agora = datetime.now()

        sessao.status = StatusSessao.REALIZADA.value
        sessao.data_realizacao = agora.date()
        sessao.hora_fim_real = agora.time()

        db.commit()
        db.refresh(sessao)

        return sessao

    @staticmethod
    def reagendar(
        db: Session,
        sessao: SessaoAssistencial,
        motivo: str = None,
    ) -> SessaoAssistencial:
        if sessao.status not in {
            StatusSessao.AGENDADA,
            StatusSessao.CONFIRMADA,
        }:
            raise ValueError(
                "Somente sessões agendadas ou confirmadas "
                "podem ser reagendadas."
            )

        sessao.status = StatusSessao.REAGENDADA.value
        sessao.motivo_reagendamento = motivo

        db.commit()
        db.refresh(sessao)

        return sessao