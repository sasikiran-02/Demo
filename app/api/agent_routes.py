"""FastAPI routes for AI agent integration with AgentCore Gateway."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.agent import AgentClient

router = APIRouter(prefix="/agent", tags=["agent"])

# Global agent client instance (lazy loaded)
_agent_client: AgentClient | None = None


async def _get_agent_client(request: Request) -> AgentClient:
    """Get or initialize the agent client."""
    global _agent_client
    
    if _agent_client is not None:
        return _agent_client
    
    try:
        # Create and initialize agent with shared app clients.
        _agent_client = AgentClient(
            okta_client=request.app.state.okta_client,
            gateway_client=request.app.state.agentcore_client,
        )
        await _agent_client.initialize()

        return _agent_client
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize agent: {str(e)}")


class AgentRequest(BaseModel):
    """Request body for asking the agent."""
    question: str


class AgentResponse(BaseModel):
    """Response from the agent."""
    answer: str
    tool_used: str | None = None


@router.post("/ask", response_model=AgentResponse)
async def ask_agent(request_body: AgentRequest, request: Request) -> AgentResponse:
    """
    Ask the AI agent a question about weather or time.
    
    The agent will automatically decide which tool to use and invoke it through the gateway
    with Okta JWT authentication.
    
    Example:
        POST /agent/ask
        {"question": "What's the weather in Seattle?"}
    """
    try:
        # Get agent client
        client = await _get_agent_client(request)
        
        # Get response from agent
        answer = await client.ask(request_body.question)
        
        return AgentResponse(
            answer=answer,
            tool_used="weather or time tools"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@router.get("/health")
async def agent_health(request: Request) -> dict:
    """Check if agent is initialized and ready."""
    try:
        client = await _get_agent_client(request)
        return {
            "status": "healthy",
            "agent_initialized": _agent_client is not None
        }
    except HTTPException:
        return {
            "status": "unhealthy",
            "error": "Agent not initialized"
        }
