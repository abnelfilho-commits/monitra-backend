"""Institutional line-scoped events, filtered by explicit temporal evidence."""
from app.services.timeline_service import TimelineService
from app.services.timeline.models import TimelineQuery, TimelineScope
from ..base_provider import BaseProvider, ProviderResult


class TimelineProvider(BaseProvider):
    code = 'TIMELINE_PROVIDER'
    version = '2.0'
    sources = None

    def collect(self, context):
        events = TimelineService.get_events(context.db, TimelineQuery(context.subject_id,
            scope=TimelineScope.CARE_LINE, requested_care_line=context.module), sources=self.sources)
        rows = []
        for e in events:
            day = e.reference_date or (e.created_at.date() if e.created_at else None)
            if day is None or not context.period_start <= day <= context.period_end:
                continue
            rows.append({'id': e.source_id, 'source_type':e.source_type.value,
                'patient_id': e.patient_id, 'care_line':e.care_line.code,
                'tipo_evento':e.event_type.value, 'data':day.isoformat(),
                'date_basis':'CLINICAL_DATE' if e.reference_date else 'CREATED_AT',
                'created_at':e.created_at.isoformat() if e.created_at else None,
                'descricao':e.summary or e.title, 'origem':e.origin, 'actor':e.actor,
                'metadata':e.metadata})
        return ProviderResult(self.code,self.version,data=rows, metadata={"total_events": len(rows)})


class CardioTimelineProvider(TimelineProvider):
    from app.services.cardio_longitudinal import CARDIO_TIMELINE_SOURCES as sources
