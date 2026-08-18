"""
Serviço de domínio responsável pelas operações do Paciente.
"""

from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.paciente import Paciente


class PatientService:
    """Centraliza recuperação e serialização de pacientes."""

    @staticmethod
    def get_by_id(
        db: Session,
        patient_id: int,
    ) -> Paciente:
        patient = (
            db.query(Paciente)
            .options(
                joinedload(Paciente.clinica),
                joinedload(Paciente.profissional),
            )
            .filter(
                Paciente.id == patient_id,
                Paciente.ativo.is_(True),
            )
            .first()
        )

        if patient is None:
            raise HTTPException(
                status_code=404,
                detail="Paciente não encontrado.",
            )

        return patient

    @staticmethod
    def serialize(patient: Paciente) -> Dict[str, Any]:
        return {
            "id": patient.id,
            "nome": patient.nome,
            "data_nascimento": (
                patient.data_nascimento.isoformat()
                if patient.data_nascimento
                else None
            ),
            "genero": patient.genero,
            "altura": (
                float(patient.altura)
                if patient.altura is not None
                else None
            ),
            "responsavel_nome": patient.responsavel_nome,
            "responsavel_email": patient.responsavel_email,
            "clinica_id": patient.clinica_id,
            "clinica_nome": (
                patient.clinica.nome
                if patient.clinica
                else None
            ),
            "profissional_id": patient.profissional_id,
            "profissional_nome": (
                patient.profissional.nome
                if patient.profissional
                else None
            ),
            "ativo": patient.ativo,
        }

    @classmethod
    def build_report_context(
        cls,
        db: Session,
        patient_id: int,
    ) -> Dict[str, Any]:
        """
        Monta o contexto básico do paciente para consumo
        pelo Framework Institucional de Conhecimento.
        """
        patient = cls.get_by_id(
            db=db,
            patient_id=patient_id,
        )

        return cls.serialize(patient)