class CareLineError(Exception):
    code = "CARE_LINE_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CareLineNotFound(CareLineError):
    code = "CARE_LINE_NOT_FOUND"


class CareLineInactive(CareLineError):
    code = "CARE_LINE_INACTIVE"


class PatientCareLineNotFound(CareLineError):
    code = "PATIENT_CARE_LINE_NOT_FOUND"


class CareLineCapabilityNotSupported(CareLineError):
    code = "CARE_LINE_CAPABILITY_NOT_SUPPORTED"


class AmbiguousCareLine(CareLineError):
    code = "AMBIGUOUS_CARE_LINE"
