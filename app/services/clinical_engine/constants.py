ASSESSMENT_LABELS = {
    "MCHAT": "M-CHAT",
    "DENVER": "Denver II",
}


def get_assessment_label(instrumento: str) -> str:
    return ASSESSMENT_LABELS.get(instrumento, instrumento)