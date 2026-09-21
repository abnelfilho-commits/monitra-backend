"""Human-facing dates only; never mutate report inputs or clinical contracts."""
from datetime import date, datetime


def format_date_pt_br(value, missing="Indisponível"):
    if value is None or value == "":
        return missing
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            pass
    return missing
