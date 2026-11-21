"""Test doubles: a scripted model, an extractor and proposals-api."""

import json
from collections.abc import Sequence
from typing import Any

from agent_framework import BaseChatClient, ChatResponse, FunctionInvocationLayer, Message

from action_agent.application.drafts import DraftIntent, DraftRejected


class ScriptedChatClient(FunctionInvocationLayer, BaseChatClient):
    """Replays scripted model turns and records what the model was sent. `_inner_get_response` is
    Agent Framework's private extension point (1.26.0); re-check it when upgrading."""

    def __init__(self, turns: Sequence[Message], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.turns, self.calls = list(turns), []

    async def _inner_get_response(self, *, messages, stream, options, **kwargs) -> ChatResponse:
        self.calls.append((list(messages), dict(options)))
        return ChatResponse(messages=[self.turns.pop(0)])


def intent_message(**fields) -> Message:
    body = {"is_draft": True, "product": "", "region": None, "new_price": None, "change_pct": None}
    return Message("assistant", [json.dumps(body | fields)])


class FakeExtractor:
    def __init__(self, **fields) -> None:
        base = {"is_draft": True, "product": "UHT milk 1 L", "region": "N"}
        base.update({"new_price": None, "change_pct": None} | fields)
        self.intent = DraftIntent(**base)

    async def extract(self, question: str) -> DraftIntent:
        return self.intent


class FakeProposals:
    def __init__(self, result) -> None:
        self.result, self.requests = result, []

    async def draft(self, request):
        self.requests.append(request)
        if isinstance(self.result, (DraftRejected, Exception)):
            raise self.result
        return self.result
