from typing import List, Optional, Union

from sqlalchemy.orm import Session

from app.models.modular import ModuloClinico, PacienteModulo

from .definitions import CareLineDefinition
from .exceptions import (
    AmbiguousCareLine,
    CareLineCapabilityNotSupported,
    CareLineInactive,
    CareLineNotFound,
    PatientCareLineNotFound,
)
from .registry import CareLineRegistry, care_line_registry


class CareLineResolver:
    def __init__(self, registry: Optional[CareLineRegistry] = None):
        self.registry = registry or care_line_registry

    def resolve(
        self,
        db: Session,
        patient_id: int,
        requested_line: Optional[Union[str, int]] = None,
        required_capability: Optional[str] = None,
    ) -> CareLineDefinition:
        if requested_line is not None:
            care_line = self.registry.get(requested_line)
            if care_line is None:
                raise CareLineNotFound(
                    "Linha de cuidado não reconhecida pela aplicação."
                )
            self._validate_definition(care_line, required_capability)
            self._validate_patient_link(db, patient_id, care_line)
            return care_line

        candidates = self._patient_candidates(db, patient_id)
        candidates = [item for item in candidates if item.active]

        if not candidates:
            raise PatientCareLineNotFound("Paciente não possui linha de cuidado ativa.")

        if required_capability is not None:
            candidates = [
                item for item in candidates if item.supports(required_capability)
            ]

        if not candidates:
            raise CareLineCapabilityNotSupported(
                "Nenhuma linha de cuidado ativa possui a capacidade solicitada."
            )

        if len(candidates) > 1:
            raise AmbiguousCareLine(
                "Paciente possui mais de uma linha de cuidado compatível; informe a linha explicitamente."
            )

        return candidates[0]

    @staticmethod
    def _validate_definition(
        care_line: CareLineDefinition,
        required_capability: Optional[str],
    ) -> None:
        if not care_line.active:
            raise CareLineInactive("Linha de cuidado está inativa na aplicação.")

        if required_capability is not None and not care_line.supports(required_capability):
            raise CareLineCapabilityNotSupported(
                "Linha de cuidado não possui a capacidade ativa para esta operação."
            )

    @staticmethod
    def _validate_patient_link(
        db: Session,
        patient_id: int,
        care_line: CareLineDefinition,
    ) -> None:
        link = (
            db.query(PacienteModulo)
            .join(ModuloClinico, ModuloClinico.id == PacienteModulo.modulo_id)
            .filter(
                PacienteModulo.paciente_id == patient_id,
                PacienteModulo.modulo_id == care_line.module_id,
                PacienteModulo.ativo.is_(True),
                ModuloClinico.ativo.is_(True),
            )
            .first()
        )
        if link is None:
            raise PatientCareLineNotFound(
                "Paciente não possui vínculo ativo com a linha de cuidado solicitada."
            )

    def _patient_candidates(
        self,
        db: Session,
        patient_id: int,
    ) -> List[CareLineDefinition]:
        module_ids = (
            db.query(PacienteModulo.modulo_id)
            .join(ModuloClinico, ModuloClinico.id == PacienteModulo.modulo_id)
            .filter(
                PacienteModulo.paciente_id == patient_id,
                PacienteModulo.ativo.is_(True),
                ModuloClinico.ativo.is_(True),
            )
            .distinct()
            .all()
        )

        candidates = []
        for row in module_ids:
            module_id = row[0]
            care_line = self.registry.get(module_id)
            if care_line is not None:
                candidates.append(care_line)
        return candidates


care_line_resolver = CareLineResolver()
