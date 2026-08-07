"""
Serviço institucional responsável pela Leitura Clínica Oficial.

Centraliza o acesso aos motores clínicos do Integra Care.
"""

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.services.neuro_engine import analisar_paciente


class ClinicalReadingService:
    """
    Obtém a Leitura Clínica Oficial dos módulos clínicos.
    """

    @staticmethod
    def get_neuro_reading(
        db: Session,
        patient_id: int,
    ) -> Dict[str, Any]:
        """
        Retorna a leitura oficial do módulo Neuro.
        """

        return analisar_paciente(
            db=db,
            paciente_id=patient_id,
        )

    @classmethod
    def build_report_context(
        cls,
        db: Session,
        patient_id: int,
        module: str,
    ) -> Dict[str, Any]:
        """
        Retorna a leitura clínica oficial do módulo.
        """

        module = (module or "").upper()

        if module == "NEURO":
            return cls.get_neuro_reading(
                db=db,
                patient_id=patient_id,
            )

        raise ValueError(
            f"Módulo clínico não suportado: {module}"
        )