from .cardio import read_cardio, read_cardio_many
from .neuro import read_neuro

# Application composition, not clinical dispatch conditionals in Core consumers.
READING_PROVIDERS = {"NEURO": read_neuro, "CARDIO": read_cardio}

BATCH_READING_PROVIDERS = {"CARDIO": read_cardio_many}
