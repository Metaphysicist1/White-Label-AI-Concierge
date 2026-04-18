from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import SystemMessage, AIMessage
from langchain_chroma import Chroma

from pydantic import BaseModel, Field
from .state import AgentState

import os
from dotenv import load_dotenv
import csv

load_dotenv()


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "db")


# hier definieren wir was Agent ausgabe soll
class RouterOutput(BaseModel):
    intent: str = Field(
        description="Classify the user intent. Must be one of: "
        "'faq' (asking about Dussmann services, jobs, locations, or company info), "
        "'lead_capture' (asking for a quote, giving contact info, OR answering YES to speaking with a human/support), "
        "'general' (saying hello, or unrelated chatter)."
    )
    language: str = Field(
        description="The language the user is speaking (e.g., 'de' or 'en')."
    )


def router_node(state: AgentState):
    print("--- Router Node ---")

    messages = state["messages"]

    llm = ChatOpenAI(
        model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY")
    )

    structured_llm = llm.with_structured_output(RouterOutput)

    system_prompt = """You are the routing brain of the Dussmann Digital Concierge. 
    You MUST read the entire conversation history, paying special attention to the LAST AI MESSAGE and the NEW USER MESSAGE.

    INTENT CLASSIFICATION RULES:
    1. 'faq' -> The user is asking a question about Dussmann services, jobs, locations, or company information.
    2. 'lead_capture' -> The user is asking for a quote, giving their contact info, OR they are saying "Yes" to speaking with a human/team member.
    3. 'general' -> Basic greetings ("hello", "hey") or unrelated chatter.

    CRITICAL OVERRIDE: If the AI recently offered to connect the user to a human (e.g., "Möchten Sie, dass ich Sie mit einem Menschen verbinde?"), and the user replies positively ("Ja", "Ja bitte", "Yes", "Please"), YOU MUST CLASSIFY THE INTENT AS 'lead_capture'.
    """

    routing_messages = [SystemMessage(content=system_prompt)] + messages

    decision = structured_llm.invoke(routing_messages)

    print((f"Decision: Intent='{decision.intent}' Language='{decision.language}' "))

    return {
        "intent": decision.intent,
        "language": decision.language,
    }


def general_node(state: AgentState):
    print("--- GENERAL CHATTER NODE ---")
    messages = state["messages"]
    language = state.get("language", "de")

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.5)

    system_prompt = f"""You are the friendly Dussmann Digital Assistant. 
    Converse naturally with the user in this language: {language}.
    You have access to the conversation history. 
    If the user is confused, politely ask if they want to know about our Services, or if they want to speak to a human team member.
    Keep your answers brief and polite."""

    response = llm.invoke([SystemMessage(content=system_prompt)] + messages)

    return {"messages": [response]}


def rag_node(state: AgentState):
    print("--- RAG Node ---")
    messages = state["messages"]
    language = state["language"]

    user_question = messages[-1].content

    optimizer_prompt = f"""
    You are a search query optimizer. 
    Convert the following user message into a clean, keyword-rich search query in GERMAN to search a corporate facility management database.
    Fix any typos. If they use English words (like 'office'), translate them to German (like 'Büro' or 'Standort').
    User message: {user_question}
    ONLY output the optimized German keywords, nothing else.
    """

    llm = ChatOpenAI(
        model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY")
    )
    optimized_query = llm.invoke(optimizer_prompt).content

    # hier machen wir die embedding
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small", api_key=os.getenv("OPENAI_API_KEY")
    )

    # hier laden wir die database
    db = Chroma(persist_directory=DB_DIR, embedding_function=embeddings)

    # suchen wir nach den besten treffern
    docs = db.similarity_search(optimized_query, k=10)

    # verbinden wir die docs zu einem string
    retrieved_context = "\n\n".join([doc.page_content for doc in docs])

    # initialisierung unseres llms
    llm = ChatOpenAI(
        model="gpt-4o-mini", temperature=0.2, api_key=os.getenv("OPENAI_API_KEY")
    )

    # unsere system prompt
    system_prompt = f"""You are the Dussmann Digital Concierge. 
    Answer the user's question ONLY using the context provided below. 
    If the answer is not in the context, politely say you don't know and offer to connect them with a human.
    
    CRITICAL: You MUST answer in this language code: {language}.
    
    CONTEXT:
    {retrieved_context}
    """

    answer_llm = ChatOpenAI(
        model="gpt-4o-mini", temperature=0.2, api_key=os.getenv("OPENAI_API_KEY")
    )
    # rufen wir unsere llm auf und geben uns die response
    response = answer_llm.invoke([SystemMessage(content=system_prompt), messages[-1]])
    final_text = response.content if hasattr(response, "content") else str(response)

    print("RAG Answer Generated: {final_text[:50]}...")

    return {"messages": [AIMessage(content=final_text)]}


# neue struktur für richtige daten extraktion
class LeadExtraction(BaseModel):
    name: str = Field(
        description="Name of the person. If not provided, output 'Unknown'"
    )
    company: str = Field(
        description="Name of the company. If not provided, output 'Unknown'"
    )
    email: str = Field(description="Email address. If not provided, output 'Unknown'")
    phone: str = Field(description="Phone number. If not provided, output 'Unknown'")
    service: str = Field(
        description="The specific Dussmann service they want (e.g., Cleaning, Security, Catering). If not provided, output 'Unknown'"
    )


# neue node für die daten extraktion
def lead_node(state: AgentState):
    print("--- Lead Node ---")
    messages = state["messages"]
    language = state["language"]

    llm = ChatOpenAI(
        model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY")
    )
    # hier extrahieren wir die daten
    extractor = llm.with_structured_output(LeadExtraction)
    extracted_data = extractor.invoke(messages[-1].content)

    # THE FIX: Print exactly what the LLM extracted so we aren't blind!
    print(
        f"Extracted Data -> Name: {extracted_data.name}, Company: {extracted_data.company}, Email: {extracted_data.email}"
    )

    missing_fields = []
    if extracted_data.name == "Unknown":
        missing_fields.append("Name")
    if extracted_data.company == "Unknown":
        missing_fields.append("Company Name (Firmenname)")
    if extracted_data.email == "Unknown" or "@" not in extracted_data.email:
        missing_fields.append("Email Address")
    if extracted_data.phone == "Unknown":
        missing_fields.append("Phone Number (Telefonnummer)")
    if extracted_data.service == "Unknown":
        missing_fields.append("Service of Interest (Gewünschter Service)")

    if missing_fields:
        slot_filling_prompt = f"""
        You are the Dussmann Assistant collecting lead information for a quote.
        You still need the following details from the user: {", ".join(missing_fields)}.
        
        CRITICAL: Ask the user for this missing information in a highly professional, conversational, and friendly way. 
        Do NOT list them like a robot. Frame it like: "To put together the perfect quote for you, I just need a few more details..."
        You MUST speak in this language: {language}.
        """
        response = ChatOpenAI(model="gpt-4o-mini", temperature=0.4).invoke(
            [SystemMessage(content=slot_filling_prompt), messages[-1]]
        )
        msg = response.content
    else:
        csv_file = os.path.join(BASE_DIR, "data", "leads.csv")
        file_exists = os.path.isfile(csv_file)

        with open(csv_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            if not file_exists:
                print(f"Creating new CSV file: {csv_file}")
                writer.writerow(["Name", "Email", "Phone", "Company", "Message"])

            writer.writerow(
                [
                    extracted_data.name,
                    extracted_data.email,
                    extracted_data.phone,
                    extracted_data.company,
                    extracted_data.message,
                ]
            )

        msg = (
            "Danke! Wir haben Ihre Anfrage gespeichert. Unser Team meldet sich in Kürze."
            if language == "de"
            else "Thanks! We've saved your request and our team will contact you shortly."
        )

    return {"messages": [AIMessage(content=msg)]}
