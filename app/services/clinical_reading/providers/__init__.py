from .cardio import read_cardio
from .neuro import read_neuro

# Application composition, not clinical dispatch conditionals in Core consumers.
READING_PROVIDERS = {"NEURO": read_neuro, "CARDIO": read_cardio}
