"""AI Agent client for interacting with AgentCore Gateway."""

from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client

from app.core.logging import get_logger
from app.gateway.agentcore_client import AgentCoreGatewayClient
from app.security.okta_client import OktaTokenClient


logger = get_logger(__name__)


class AgentClient:
    """Manages the AI agent and its connection to the gateway."""

    def __init__(self, okta_client: OktaTokenClient, gateway_client: AgentCoreGatewayClient):
        """Initialize the agent client."""
        self._okta_client = okta_client
        self._gateway_client = gateway_client
        self._agent = None
        self._mcp_client = None
        self._transport = None
        self._mcp_client_open = False
        self._tool_names: list[str] = []

    async def initialize(self) -> None:
        """Initialize the agent and connect to gateway."""
        if self._agent is not None:
            return  # Already initialized

        try:
            logger.info("Getting Okta access token...")
            token, _ = await self._okta_client.get_token()
            logger.info("Access token obtained")

            # Create MCP transport with authentication
            logger.info("Creating MCP transport...")
            self._transport = streamablehttp_client(
                self._gateway_client.gateway_url,
                headers=self._gateway_client.build_auth_headers(token.access_token),
            )
            logger.info("Transport created")

            # Initialize Bedrock model
            logger.info("Initializing Bedrock model...")
            model = BedrockModel(
                model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
                temperature=0.7,
                streaming=True,
            )
            logger.info("Model initialized")

            # Create MCP client
            logger.info("Creating MCP client...")
            self._mcp_client = MCPClient(lambda: self._transport)
            logger.info("MCP client created")

            # Keep client context open for subsequent tool execution.
            self._mcp_client.__enter__()
            self._mcp_client_open = True

            logger.info("Discovering tools...")
            tools = self._mcp_client.list_tools_sync()
            self._tool_names = [getattr(tool, "tool_name", str(tool)) for tool in tools]
            logger.info("Connected to gateway with %s tools", len(self._tool_names))

            logger.info("Available tools:")
            for i, tool_name in enumerate(self._tool_names, 1):
                logger.info("  %s. %s", i, tool_name)

            # Create agent with discovered tools
            self._agent = Agent(model=model, tools=tools)
            logger.info("==================================================")
            logger.info("AI Agent Ready!")
            logger.info("Ask questions about weather or time.")
            logger.info("==================================================")

        except Exception as e:
            raise RuntimeError(f"Failed to initialize agent: {str(e)}")

    async def ask(self, question: str) -> str:
        """Ask the agent a question and get a response."""
        if self._agent is None:
            await self.initialize()

        try:
            logger.info("You: %s", question)
            response = self._agent(question)
            logger.info("Agent response generated")
            return str(response) if response else "No response from agent"
        except Exception as e:
            raise RuntimeError(f"Agent error: {str(e)}")

    async def close(self) -> None:
        """Clean up resources."""
        if self._mcp_client is not None:
            if self._mcp_client_open and hasattr(self._mcp_client, "__exit__"):
                self._mcp_client.__exit__(None, None, None)
                self._mcp_client_open = False
            if hasattr(self._mcp_client, "close"):
                await self._mcp_client.close()
        self._agent = None
        self._mcp_client = None
        self._transport = None
        self._tool_names = []
