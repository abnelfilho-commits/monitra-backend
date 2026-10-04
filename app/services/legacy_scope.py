"""SQL-only legacy ancestry predicates; never authorization or context inference."""
from app.models.pts import PTS, PTSObjetivo
from app.models.agenda_cuidado import AgendaCuidado
from app.models.sessao_assistencial import SessaoAssistencial


def legacy_agenda():
    # Check both persisted ancestors. Existing orphan/error semantics are retained.
    return (~AgendaCuidado.pts.has(PTS.contexto_assistencial_id.is_not(None)) &
            ~AgendaCuidado.objetivo.has(PTSObjetivo.pts.has(PTS.contexto_assistencial_id.is_not(None))))


def legacy_session():
    return ~SessaoAssistencial.agenda_cuidado.has(~legacy_agenda())
