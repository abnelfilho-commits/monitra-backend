from .neuro import NeuroDailyRecordProvider
from .cardio import CardioDailyRecordProvider

PROVIDERS = {'NEURO': NeuroDailyRecordProvider(), 'CARDIO': CardioDailyRecordProvider()}
