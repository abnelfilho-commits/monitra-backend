class DailyRecordError(ValueError):
    code = 'DAILY_RECORD_ERROR'


class DailyRecordFormNotFound(DailyRecordError):
    code = 'DAILY_RECORD_FORM_NOT_FOUND'


class AmbiguousDailyRecordForm(DailyRecordError):
    code = 'AMBIGUOUS_DAILY_RECORD_FORM'


class InvalidDailyRecordPayload(DailyRecordError):
    code = 'INVALID_DAILY_RECORD_PAYLOAD'


class DailyRecordIdentityConflict(DailyRecordError):
    code = 'DAILY_RECORD_IDENTITY_CONFLICT'


class DailyRecordNotFound(DailyRecordError):
    code = 'DAILY_RECORD_NOT_FOUND'


class DuplicateDailyRecord(DailyRecordError):
    code = 'DUPLICATE_DAILY_RECORD'
