from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    # hier speichern wir die messages direkt in unserer state
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # hier definieren wir was unsere Agent machen soll
    intent: str

    # hier mussen wir die Sprache herausfinden
    language: str

    # sammeln wir daten fur weitere verarbeitung
    lead_data: dict[str, str]
