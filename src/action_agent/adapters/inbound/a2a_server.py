"""A2A server for the action agent, behind the shared token middleware. Replies are one data part
in the shared AgentReply contract."""

import logging

from a2a.helpers import new_data_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from margin_copilot_shared.security.middleware import AuthMiddleware
from margin_copilot_shared.security.tokens import TokenValidator
from starlette.applications import Starlette
from starlette.middleware import Middleware

from action_agent.application.drafts import Drafter

log = logging.getLogger(__name__)


class ActionAgentFailed(Exception):
    def __init__(self) -> None:
        super().__init__("action-agent failed")  # a2a-sdk sends str(exception) to the caller


class ActionAgentExecutor(AgentExecutor):
    def __init__(self, drafter: Drafter) -> None:
        self._drafter = drafter

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        try:
            reply = await self._drafter.reply(context.get_user_input())
        except Exception as error:
            log.warning("draft failed: %s", type(error).__name__)
            raise ActionAgentFailed from None
        await event_queue.enqueue_event(new_data_message(reply.model_dump()))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("action-agent replies in one message; nothing to cancel")


def agent_card(public_url: str) -> AgentCard:
    return AgentCard(
        name="action-agent",
        description="Drafts pending price-change proposals for the signed-in user.",
        version="0.1.0",
        default_input_modes=["text/plain"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(protocol_binding="JSONRPC", url=public_url, protocol_version="1.0")
        ],
        skills=[
            AgentSkill(
                id="drafts",
                name="Price-change drafts",
                description="Drafts a pending price-change proposal; a person approves it on the "
                "approval screen.",
                tags=["drafts", "pricing"],
            )
        ],
    )


def create_a2a_app(drafter: Drafter, validator: TokenValidator, public_url: str) -> Starlette:
    card = agent_card(public_url)
    handler = DefaultRequestHandler(
        agent_executor=ActionAgentExecutor(drafter),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    return Starlette(
        routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")],
        middleware=[
            Middleware(
                AuthMiddleware,
                validator=validator,
                public_paths=frozenset({AGENT_CARD_WELL_KNOWN_PATH}),
            )
        ],
    )
