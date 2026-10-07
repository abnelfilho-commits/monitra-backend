ASSESSMENT_LABELS = {
    "GAD7": "GAD-7",
    "PHQ9": "PHQ-9",
    "MCHAT": "M-CHAT",
    "DENVER": "Denver II",
}


def get_assessment_label(instrumento: str) -> str:
    return ASSESSMENT_LABELS.get(instrumento, instrumento)