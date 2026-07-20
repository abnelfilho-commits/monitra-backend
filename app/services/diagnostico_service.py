from typing import List

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

        diagnostico = Diagnostico(
            paciente_id=payload.paciente_id,
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

        db.add(diagnostico)
        db.commit()
        db.refresh(diagnostico)

        return diagnostico

    @staticmethod
    def buscar_por_id(
        db: Session,
        diagnostico_id: int,
    ) -> Diagnostico:
        diagnostico = (
            db.query(Diagnostico)
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
            db.query(Diagnostico)
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

        db.commit()
        db.refresh(diagnostico)

        return diagnostico

    @staticmethod
    def cancelar(
        db: Session,
        diagnostico_id: int,
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

        if diagnostico.status == "CANCELADO":
            raise HTTPException(
                status_code=409,
                detail="Este diagnóstico já está cancelado.",
            )

        diagnostico.status = "CANCELADO"

        db.commit()
        db.refresh(diagnostico)

        return diagnostico

    @staticmethod
    def revisar(
        db: Session,
        diagnostico_id: int,
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

        if diagnostico.status == "CANCELADO":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Um diagnóstico cancelado não pode "
                    "ser marcado como revisado."
                ),
            )

        diagnostico.status = "REVISADO"

        db.commit()
        db.refresh(diagnostico)

        return diagnostico