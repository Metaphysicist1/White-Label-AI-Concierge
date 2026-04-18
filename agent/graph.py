from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import router_node, rag_node, lead_node, general_node
from langgraph.checkpoint.memory import MemorySaver


# hier definieren wir unsere nachfolgenden schritte
def route_next_step(state: AgentState):

    intent = state["intent"]

    if intent == "faq":
        return "rag"
    elif intent == "lead_capture":
        return "lead"
    else:
        return "general"


# die haupt funktion um unsere graph zu erstellen
def build_graph():
    memory = MemorySaver()

    # initialisieren wir unseren graph
    workflow = StateGraph(AgentState)

    # hier fügen wir unsere nodes hinzu
    workflow.add_node("router", router_node)
    workflow.add_node("rag", rag_node)
    workflow.add_node("general", general_node)
    workflow.add_node("lead", lead_node)

    workflow.set_entry_point("router")

    # schritt bei welchem node wir weitergehen wenn wir auf router node kommen
    workflow.add_conditional_edges(
        "router",
        route_next_step,
        {
            "rag": "rag",
            "general": "general",
            "lead": "lead",
        },
    )

    workflow.add_edge("rag", END)
    workflow.add_edge("general", END)
    workflow.add_edge("lead", END)

    return workflow.compile(checkpointer=memory)
