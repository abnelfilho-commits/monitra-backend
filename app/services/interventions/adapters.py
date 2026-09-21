"""Physical persistence adapters. Never commit or roll back."""
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, select
from app.models.intervencao import Intervencao
from app.models.profissional import Profissional
from .models import InterventionRecord, SourceType, CareLineAssociation
from .exceptions import InvalidInterventionPayload


def actor(namespace, identity):
    return {'namespace': namespace, 'id': identity} if identity is not None else None


class GenericAdapter:
    source_type = SourceType.GENERIC_INTERVENTION

    def get(self, db, identity, lock=False):
        query = db.query(Intervencao).filter(Intervencao.id == identity)
        return (query.with_for_update() if lock else query).first()

    def list_for_patient(self, db, patient_id):
        return db.query(Intervencao).filter(Intervencao.paciente_id == patient_id).order_by(
            Intervencao.data_intervencao.desc()).all()

    def to_record(self, row, registry):
        line = registry.get(row.modulo_id)
        if line is None:
            raise InvalidInterventionPayload('Intervenção sem linha válida.')
        return InterventionRecord(self.source_type, row.id, row.paciente_id,
            line, row.modulo_id, CareLineAssociation.EXPLICIT,
            actor('usuarios', row.profissional_id), row.tipo, row.descricao,
            row.data_intervencao, row.created_at)

    def create(self, db, submission, line, user, patient):
        if submission.reference_datetime is None:
            raise InvalidInterventionPayload('Data clínica é obrigatória para intervenção genérica.')
        if submission.payload:
            raise InvalidInterventionPayload('Intervenção genérica não aceita campos especializados.')
        row = Intervencao(paciente_id=patient.id, modulo_id=line.module_id,
            profissional_id=user.id, tipo=submission.type, descricao=submission.narrative,
            data_intervencao=submission.reference_datetime)
        db.add(row)
        db.flush()
        return row

    def update(self, db, row, changes):
        row.tipo = changes.type
        row.descricao = changes.narrative
        row.data_intervencao = changes.reference_datetime
        db.flush()
        return row

    def delete(self, db, row):
        db.delete(row)
        db.flush()


# Typed SQL projection of the existing table, not an ORM model or schema creator.
CARDIO_TABLE = Table('intervencoes_cardiometabolicas', MetaData(),
    Column('id', Integer, primary_key=True), Column('paciente_id', Integer, nullable=False),
    Column('modulo_id', Integer, nullable=False),
    Column('tipo', String, nullable=False),
    Column('descricao', Text), Column('prioridade', String),
    Column('created_at', DateTime(timezone=True)))


class CardioAdapter:
    source_type = SourceType.CARDIO_INTERVENTION

    def get(self, db, identity, lock=False):
        query = select(CARDIO_TABLE).where(CARDIO_TABLE.c.id == identity)
        return db.execute(query.with_for_update() if lock else query).mappings().first()

    def list_for_patient(self, db, patient_id):
        return db.execute(select(CARDIO_TABLE).where(CARDIO_TABLE.c.paciente_id == patient_id)
            .order_by(CARDIO_TABLE.c.created_at.desc())).mappings().all()

    def to_record(self, row, registry):
        line = registry.get(row['modulo_id'])
        if line is None or line.code != 'CARDIO':
            raise InvalidInterventionPayload('Intervenção Cardio com linha incompatível.')
        return InterventionRecord(self.source_type, row['id'], row['paciente_id'], line,
            line.module_id, CareLineAssociation.EXPLICIT,
            None, row['tipo'], row['descricao'],
            None, row['created_at'], {'priority': row['prioridade']})

    def create(self, db, submission, line, user, patient):
        if submission.reference_datetime is not None:
            raise InvalidInterventionPayload('Intervenção Cardio não suporta data clínica independente.')
        if set(submission.payload) - {'priority'}:
            raise InvalidInterventionPayload('Campo especializado Cardio não suportado.')
        priority = submission.payload.get('priority', 'moderada')
        if not isinstance(priority, str) or len(priority) > 30:
            raise InvalidInterventionPayload('Prioridade deve ser texto de até 30 caracteres.')
        if len(submission.type) > 100 or submission.narrative is None:
            raise InvalidInterventionPayload('Cardio exige descrição e tipo de até 100 caracteres.')
        professional_id = user.profissional_id
        if professional_id is not None:
            professional = db.query(Profissional).filter(Profissional.id == professional_id).first()
            if professional is None or not professional.ativo or professional.clinica_id != patient.clinica_id:
                raise InvalidInterventionPayload('Vínculo profissional incompatível ou inativo.')
        # Authorization above does not establish persisted authorship: this table
        # has no author column. Reads explicitly return actor=None.
        # Omit created_at: preserve the database default, not an application clock.
        row = db.execute(CARDIO_TABLE.insert().values(paciente_id=patient.id, modulo_id=line.module_id,
            tipo=submission.type,
            descricao=submission.narrative, prioridade=priority).returning(*CARDIO_TABLE.c)).mappings().one()
        db.flush()
        return row
