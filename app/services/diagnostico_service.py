from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.diagnostico import Diagnostico
from app.models.paciente import Paciente
from app.schemas.diagnostico import (
    DiagnosticoCreate,
    DiagnosticoUpdate,
)


class DiagnosticoService:
    """
    Regras de negócio para Diagnósticos Clínicos.

    O diagnóstico é opcional dentro da jornada assistencial.
    Este serviço preserva o histórico clínico e evita exclusão física.
    """

    @staticmethod
    def criar(
        db: Session,
        payload: DiagnosticoCreate,
        module_id: int,
        *,
        commit: bool = True,
    ) -> Diagnostico:
        paciente = (
            db.query(Paciente)
            .filter(Paciente.id == payload.paciente_id)
            .first()
        )

        if not paciente:
            raise HTTPException(
                status_code=404,
                detail="Paciente não encontrado.",
            )

        diagnostico = DiagnosticoService._novo(payload, module_id)
        db.add(diagnostico)
        return DiagnosticoService._finalizar(db, diagnostico, commit=commit)

    @staticmethod
    def _novo(payload, module_id, contexto_assistencial_id=None):
        return Diagnostico(
            contexto_assistencial_id=contexto_assistencial_id,
            paciente_id=payload.paciente_id,
            modulo_id=module_id,
            tipo=payload.tipo,
            status=payload.status,
            cid=payload.cid,
            descricao_clinica=payload.descricao_clinica,
            data_diagnostico=payload.data_diagnostico,
            medico_nome=payload.medico_nome,
            medico_especialidade=payload.medico_especialidade,
            medico_crm=payload.medico_crm,
            medico_cpf=payload.medico_cpf,
            observacoes=payload.observacoes,
        )

    @staticmethod
    def _finalizar(db, diagnostico, *, commit):
        if commit:
            db.commit()
            db.refresh(diagnostico)
        else:
            db.flush()
        return diagnostico

    @staticmethod
    def buscar_por_id(
        db: Session,
        diagnostico_id: int,
    ) -> Diagnostico:
        diagnostico = (
            db.query(Diagnostico).filter(Diagnostico.contexto_assistencial_id.is_(None))
            .filter(Diagnostico.id == diagnostico_id)
            .first()
        )

        if not diagnostico:
            raise HTTPException(
                status_code=404,
                detail="Diagnóstico não encontrado.",
            )

        return diagnostico

    @staticmethod
    def listar_por_paciente(
        db: Session,
        paciente_id: int,
    ) -> List[Diagnostico]:
        paciente = (
            db.query(Paciente)
            .filter(Paciente.id == paciente_id)
            .first()
        )

        if not paciente:
            raise HTTPException(
                status_code=404,
                detail="Paciente não encontrado.",
            )

        return (
            db.query(Diagnostico).filter(Diagnostico.contexto_assistencial_id.is_(None))
            .filter(
                Diagnostico.paciente_id == paciente_id
            )
            .order_by(
                Diagnostico.data_diagnostico.desc(),
                Diagnostico.created_at.desc(),
            )
            .all()
        )

    @staticmethod
    def atualizar(
        db: Session,
        diagnostico_id: int,
        payload: DiagnosticoUpdate,
        *,
        commit: bool = True,
    ) -> Diagnostico:
        diagnostico = (
            DiagnosticoService.buscar_por_id(
                db=db,
                diagnostico_id=diagnostico_id,
            )
        )

        dados = payload.model_dump(
            exclude_unset=True,
        )

        for campo, valor in dados.items():
            setattr(
                diagnostico,
                campo,
                valor,
            )

        return DiagnosticoService._finalizar(db, diagnostico, commit=commit)

    @staticmethod
    def cancelar(
        db: Session,
        diagnostico_id: int,
        *,
        commit: bool = True,
    ) -> Diagnostico:
        """
        Cancela logicamente o diagnóstico.

        Não excluímos fisicamente porque o diagnóstico
        faz parte da história clínica longitudinal.
        """

        diagnostico = (
            DiagnosticoService.buscar_por_id(
                db=db,
                diagnostico_id=diagnostico_id,
            )
        )

        DiagnosticoService._aplicar_cancelar(diagnostico)
        return DiagnosticoService._finalizar(db, diagnostico, commit=commit)

    @staticmethod
    def _aplicar_cancelar(diagnostico):
        if diagnostico.status == "CANCELADO":
            raise HTTPException(
                status_code=409,
                detail="Este diagnóstico já está cancelado.",
            )

        diagnostico.status = "CANCELADO"

    @staticmethod
    def revisar(
        db: Session,
        diagnostico_id: int,
        *,
        commit: bool = True,
    ) -> Diagnostico:
        """
        Marca o diagnóstico como revisado.

        Útil quando um novo diagnóstico substitui ou
        complementa uma avaliação anterior.
        """

        diagnostico = (
            DiagnosticoService.buscar_por_id(
                db=db,
                diagnostico_id=diagnostico_id,
            )
        )

        DiagnosticoService._aplicar_revisar(diagnostico)
        return DiagnosticoService._finalizar(db, diagnostico, commit=commit)

    @staticmethod
    def _aplicar_revisar(diagnostico):
        if diagnostico.status == "CANCELADO":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Um diagnóstico cancelado não pode "
                    "ser marcado como revisado."
                ),
            )

        diagnostico.status = "REVISADO"

    # Internal persistence primitives, NOT authorization or an operational endpoint.
    # The future caller must validate Context/Line, run the W1B evaluator and
    # stabilize/revalidate the transaction before calling these methods.
    # None of these methods commits, rolls back, retries or grants ADMIN bypass.
    @staticmethod
    def _exigir_identidade_contextual(contexto_assistencial_id, paciente_id, modulo_id):
        if any(type(value) is not int or value <= 0 for value in
               (contexto_assistencial_id, paciente_id, modulo_id)):
            raise ValueError("Contexto, paciente e módulo explícitos são obrigatórios.")

    @staticmethod
    def _criar_contextual(db, payload: DiagnosticoCreate, *, contexto_assistencial_id, modulo_id):
        DiagnosticoService._exigir_identidade_contextual(
            contexto_assistencial_id, payload.paciente_id, modulo_id)
        diagnostico = DiagnosticoService._novo(payload, modulo_id, contexto_assistencial_id)
        db.add(diagnostico)
        # Existing W1C-H composite FKs/checks enforce Context/Patient/Line.
        return DiagnosticoService._finalizar(db, diagnostico, commit=False)

    @staticmethod
    def _buscar_contextual(db, diagnostico_id, *, contexto_assistencial_id, paciente_id, modulo_id):
        DiagnosticoService._exigir_identidade_contextual(
            contexto_assistencial_id, paciente_id, modulo_id)
        diagnostico = db.query(Diagnostico).filter_by(
            id=diagnostico_id, contexto_assistencial_id=contexto_assistencial_id,
            paciente_id=paciente_id, modulo_id=modulo_id).first()
        if diagnostico is None:
            raise HTTPException(404, "Diagnóstico não encontrado.")
        return diagnostico

    @staticmethod
    def _atualizar_contextual(db, diagnostico_id, dados: dict, *,
                             contexto_assistencial_id, paciente_id, modulo_id):
        # Validate raw internal changes before the legacy schema could ignore extras.
        if set(dados) & {"contexto_assistencial_id", "paciente_id", "modulo_id"}:
            raise ValueError("A identidade contextual do diagnóstico é imutável.")
        if set(dados) - set(DiagnosticoUpdate.model_fields):
            raise ValueError("Campo de diagnóstico não suportado.")
        payload = DiagnosticoUpdate.model_validate(dados)
        diagnostico = DiagnosticoService._buscar_contextual(db, diagnostico_id,
            contexto_assistencial_id=contexto_assistencial_id,
            paciente_id=paciente_id, modulo_id=modulo_id)
        for campo, valor in payload.model_dump(exclude_unset=True).items():
            setattr(diagnostico, campo, valor)
        return DiagnosticoService._finalizar(db, diagnostico, commit=False)

    @staticmethod
    def _cancelar_contextual(db, diagnostico_id, *, contexto_assistencial_id, paciente_id, modulo_id):
        diagnostico = DiagnosticoService._buscar_contextual(db, diagnostico_id,
            contexto_assistencial_id=contexto_assistencial_id,
            paciente_id=paciente_id, modulo_id=modulo_id)
        DiagnosticoService._aplicar_cancelar(diagnostico)
        return DiagnosticoService._finalizar(db, diagnostico, commit=False)

    @staticmethod
    def _revisar_contextual(db, diagnostico_id, *, contexto_assistencial_id, paciente_id, modulo_id):
        diagnostico = DiagnosticoService._buscar_contextual(db, diagnostico_id,
            contexto_assistencial_id=contexto_assistencial_id,
            paciente_id=paciente_id, modulo_id=modulo_id)
        DiagnosticoService._aplicar_revisar(diagnostico)
        return DiagnosticoService._finalizar(db, diagnostico, commit=False)

    @staticmethod
    def serializar_para_relatorio(
        diagnostico: Diagnostico,
    ) -> Dict[str, Any]:
        """
        Serializa o diagnóstico para consumo pelo
        Framework Institucional de Conhecimento.
        """

        return {
            "id": diagnostico.id,
            "paciente_id": diagnostico.paciente_id,
            "tipo": diagnostico.tipo,
            "status": diagnostico.status,
            "cid": diagnostico.cid,
            "descricao_clinica": diagnostico.descricao_clinica,
            "data_diagnostico": (
                diagnostico.data_diagnostico.isoformat()
                if diagnostico.data_diagnostico
                else None
            ),
            "medico_nome": diagnostico.medico_nome,
            "medico_especialidade": diagnostico.medico_especialidade,
            "medico_crm": diagnostico.medico_crm,
            "observacoes": diagnostico.observacoes,
            "created_at": (
                diagnostico.created_at.isoformat()
                if diagnostico.created_at
                else None
            ),
            "updated_at": (
                diagnostico.updated_at.isoformat()
                if diagnostico.updated_at
                else None
            ),
        }

    @classmethod
    def build_report_context(
        cls,
        db: Session,
        patient_id: int,
    ) -> Dict[str, Any]:
        """
        Monta o contexto diagnóstico completo do paciente.
        """

        diagnosticos = cls.listar_por_paciente(
            db=db,
            paciente_id=patient_id,
        )

        historico = [
            cls.serializar_para_relatorio(diagnostico)
            for diagnostico in diagnosticos
        ]

        ativos = [
            diagnostico
            for diagnostico in historico
            if diagnostico["status"] == "ATIVO"
        ]

        revisados = [
            diagnostico
            for diagnostico in historico
            if diagnostico["status"] == "REVISADO"
        ]

        cancelados = [
            diagnostico
            for diagnostico in historico
            if diagnostico["status"] == "CANCELADO"
        ]

        return {
            "ativos": ativos,
            "revisados": revisados,
            "cancelados": cancelados,
            "historico": historico,
            "total_diagnosticos": len(historico),
        }