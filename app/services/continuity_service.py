"""Institutional continuity classification, independent of clinical interpretation."""

def classify_continuity(days_without_record):
    if days_without_record is None:
        return 'NAO_INICIADA'
    if days_without_record >= 7:
        return 'CRITICA'
    if days_without_record >= 4:
        return 'ATENCAO'
    return 'REGULAR'


def continuity_signal(reference_date, today):
    days = (today - reference_date).days if reference_date is not None else None
    return {'classification': classify_continuity(days), 'days_without_record': days,
            'reference_date': reference_date}
