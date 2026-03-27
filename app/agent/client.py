"""AI Agent client for interacting with AgentCore Gateway."""

from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client

from app.core.logging import get_logger
from app.gateway.agentcore_client import AgentCoreGatewayClient

from app.security.okta_client import OktaTokenClient
from app.security.jwt_validator import JWTValidator


logger = get_logger(__name__)


class AgentClient:
    """Manages the AI agent and its connection to the gateway."""

    def __init__(self, okta_client: OktaTokenClient, gateway_client: AgentCoreGatewayClient, jwt_validator: JWTValidator):
        """Initialize the agent client."""
        self._okta_client = okta_client
        self._gateway_client = gateway_client
        self._jwt_validator = jwt_validator
        self._agent = None
        self._mcp_client = None
        self._transport = None
        self._mcp_client_open = False
        self._tool_names: list[str] = []
        self._token = None
        self._token_expiry = None

    async def initialize(self) -> None:
        """Initialize the agent and connect to gateway."""
        if self._agent is not None:
            return  # Already initialized

        import traceback
        try:
            logger.info("Getting Okta access token...")
            token, _ = await self._okta_client.get_token()
            logger.info("Access token obtained")

            logger.info("Validating access token locally before creating transport...")
            await self._jwt_validator.validate(token.access_token)
            logger.info("Token validated successfully.")

            # Store token and expiry
            self._token = token.access_token
            # Decode JWT to get expiry (exp)
            import jwt
            try:
                payload = jwt.decode(self._token, options={"verify_signature": False})
                self._token_expiry = payload.get("exp")
            except Exception as e:
                logger.warning(f"Could not decode token expiry: {e}")
                self._token_expiry = None

            # Create MCP transport with authentication
            logger.info("Creating MCP transport...")
            self._transport = streamablehttp_client(
                self._gateway_client.gateway_url,
                headers=self._gateway_client.build_auth_headers(self._token),
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

        except AppError:
            # Let AppError propagate so FastAPI can handle it
            raise
        except Exception as e:
            logger.error("Agent initialization failed: %s\n%s", str(e), traceback.format_exc())
            raise RuntimeError(f"Failed to initialize agent: {str(e)}")

    async def refresh_token(self) -> None:
        """Refresh the token and update transport, preserving agent context."""
        logger.info("Refreshing token only (preserving agent context)...")
        token, _ = await self._okta_client.get_token()
        await self._jwt_validator.validate(token.access_token)
        self._token = token.access_token
        import jwt
        try:
            payload = jwt.decode(self._token, options={"verify_signature": False})
            self._token_expiry = payload.get("exp")
        except Exception as e:
            logger.warning(f"Could not decode token expiry: {e}")
            self._token_expiry = None
        # Update transport and MCP client headers
        self._transport = streamablehttp_client(
            self._gateway_client.gateway_url,
            headers=self._gateway_client.build_auth_headers(self._token),
        )
        if self._mcp_client is not None:
            self._mcp_client._transport_factory = lambda: self._transport

    async def ask(self, question: str) -> str:
        """Ask the agent a question and get a response. Validate token before use; refresh if expired."""
        # Validate token before each question
        try:
            await self._jwt_validator.validate(self._token)
        except Exception as e:
            logger.info(f"Token validation failed: {e}. Refreshing token only...")
            await self.refresh_token()

        import traceback
        try:
            logger.info("You: %s", question)
            response = self._agent(question)
            logger.info("Agent response generated")
            return str(response) if response else "No response from agent"
        except Exception as e:
            # Log full stack trace for debugging
            logger.error("Agent error: %s\n%s", str(e), traceback.format_exc())
            # Still fallback to error-based refresh for robustness
            error_message = str(e).lower()
            if "token" in error_message and ("expire" in error_message or "invalid" in error_message or "401" in error_message or "forbidden" in error_message):
                logger.warning("Token expired or invalid (detected by error). Refreshing token and re-initializing agent...")
                await self.close()
                await self.initialize()
                try:
                    response = self._agent(question)
                    logger.info("Agent response generated after token refresh")
                    return str(response) if response else "No response from agent"
                except Exception as e2:
                    logger.error("Agent error after token refresh: %s\n%s", str(e2), traceback.format_exc())
                    raise RuntimeError(f"Agent error after token refresh: {str(e2)}")
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
        self._token = None
        self._token_expiry = None
