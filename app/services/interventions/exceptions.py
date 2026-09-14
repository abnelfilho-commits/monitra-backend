"""Intervention errors; care-line resolution retains Wave 1 errors."""
class InterventionError(Exception):
    code = 'INTERVENTION_ERROR'


class InterventionNotFound(InterventionError):
    code = 'INTERVENTION_NOT_FOUND'


class InterventionIdentityConflict(InterventionError):
    code = 'INTERVENTION_IDENTITY_CONFLICT'


class InvalidInterventionPayload(InterventionError):
    code = 'INVALID_INTERVENTION_PAYLOAD'


class InterventionOperationNotSupported(InterventionError):
    code = 'INTERVENTION_OPERATION_NOT_SUPPORTED'
