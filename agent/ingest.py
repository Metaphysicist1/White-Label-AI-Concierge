import json
import os
from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print(f"Base directory: {BASE_DIR}")
DATA_DIR = os.path.join(BASE_DIR, "scraper", "data")
print(f"Data directory: {DATA_DIR}")
DB_DIR = os.path.join(BASE_DIR, "db")
print(f"Database directory: {DB_DIR}")

print(f"OpenAI API key: {os.getenv('OPENAI_API_KEY')}")

def load_data():
    with open("scraper/data/knowledge.json", 'r', encoding='utf-8') as f:
        print(f"Loading data from {DATA_DIR}")
        scrapped_data = json.load(f)

    documents = []
    for item in scrapped_data:
        doc = Document(
            page_content=item["content"],
            metadata={"source": item["url"], "title": item["title"]}
        )
        documents.append(doc)
    return documents

def chunk_documents(documents):
    print("chunking Docuemnts...")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=150, 
        length_function=len
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Split {len(documents)} documents into {len(chunks)} chunks")
    return chunks

def build_vector_database(chunks):
    print("Initializing OpenAI Embeddings...")

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", api_key=os.getenv("OPENAI_API_KEY"))

    print(f"Building local Chroma Vector database at {DB_DIR}")

    db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=DB_DIR    
    )
    print("Database built and persisted successfully!")

def main():
    if not os.path.exists(DATA_DIR):
        print(f"Error: Could not find {DATA_DIR}. Did you run the scraper?")
        return

    documents = load_data()
    chunks = chunk_documents(documents)
    build_vector_database(chunks)

if __name__ == "__main__":
    main()
