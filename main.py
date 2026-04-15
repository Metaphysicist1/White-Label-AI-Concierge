from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent.graph import build_graph
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

# Load your API keys
load_dotenv()

# Initialize the LangGraph agent
agent_app = build_graph()

# Initialize FastAPI
app = FastAPI(title="Dussmann API")

# VERY IMPORTANT: CORS Middleware prevents browser blocking issues
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define the expected JSON payload from the frontend
class ChatRequest(BaseModel):
    message: str

# 1. Serve the UI Frontend
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

# 2. The Chat Endpoint (Connecting Frontend to LangGraph)
@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    print(f"\nReceived message: {request.message}")

    try:
        # Format the message for LangGraph
        state = {"messages": [HumanMessage(content=request.message)]}
        
        config = {"configurable": {"thread_id": "interview_1"}}
        
        # Invoke the graph
        result = agent_app.invoke(state, config=config)

        final_message = result["messages"][-1]
        

        if isinstance(final_message, HumanMessage):
            print("CRITICAL: Graph did not append an AIMessage!")
            return {"response": "Error: The AI Agent failed to process the request. Please check the backend terminal for logs."}
        
        return {"response": final_message.content}
    
    except Exception as e:
        print(f"Error: {e}")
        return {"response": "Sorry, I'm having trouble processing your request. Please try again later."}

if __name__ == "__main__":
    import uvicorn
    # Run the server. It will automatically reload if you change the code.
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)