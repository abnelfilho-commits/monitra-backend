"""
Knowledge Engine responsável pela síntese
do Diagnóstico Clínico.
"""

from ..context import ReportContext

from .base_knowledge_engine import BaseKnowledgeEngine
from .knowledge_result import KnowledgeResult
from .models import DiagnosisSummaryModel


class DiagnosisSummaryEngine(BaseKnowledgeEngine):
    """
    Produz a síntese do diagnóstico clínico ativo
    para a visão profissional.
    """

    code = "DIAGNOSIS_SUMMARY_ENGINE"
    version = "1.0"

    def execute(
        self,
        context: ReportContext,
    ) -> KnowledgeResult:

        diagnosis_context = context.collected_data.get(
            "DIAGNOSIS_PROVIDER",
            {},
        )

        active_diagnoses = diagnosis_context.get(
            "ativos",
            [],
        )

        active_diagnosis = (
            active_diagnoses[0]
            if active_diagnoses
            else None
        )

        if active_diagnosis is None:

            model = DiagnosisSummaryModel(
                has_active_diagnosis=False,
            )

        else:

            model = DiagnosisSummaryModel(
                has_active_diagnosis=True,

                cid=active_diagnosis.get(
                    "cid"
                ),

                clinical_description=active_diagnosis.get(
                    "descricao_clinica"
                ),

                diagnosis_date=active_diagnosis.get(
                    "data_diagnostico"
                ),

                physician_name=active_diagnosis.get(
                    "medico_nome"
                ),

                physician_specialty=active_diagnosis.get(
                    "medico_especialidade"
                ),

                physician_registry=active_diagnosis.get(
                    "medico_crm"
                ),
            )

        return KnowledgeResult(
            engine_code=self.code,
            engine_version=self.version,
            knowledge=[
                model,
            ],
        )