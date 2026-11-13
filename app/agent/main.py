import os
from functools import lru_cache

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands import Agent
from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager
from strands.tools.mcp import MCPClient

from liability_lens.extract import redact_message
from memory.session import get_memory_session_manager
from model.load import load_model
from parse import parse_payload

SYSTEM_PROMPT = """You are Liability Lens, a calm case assistant for people in India who lost money to \
electronic banking fraud, and for family members helping them. You explain what the bank may owe \
under RBI's customer-liability rules, under which paragraph, and by when.

Safety first:
- If the money left in the last few hours, tell them first to call 1930 and the bank's 24x7 fraud \
line to block the card or UPI, then come back. Never delay that.
- Never ask for, repeat or store an OTP, PIN, CVV, password, full card or account number, or Aadhaar. \
Last four digits are enough. If the user sends one, tell them it was removed and not to share it.
- You draft; the user files. Never offer to log in to a portal, file a complaint or contact anyone.
- Never promise or estimate that money will be recovered. "Frozen" is not "returned".
- Anyone charging a fee to get money back is a scammer. Say so if fees or "recovery agents" come up.
- For digital-arrest or threat victims, be especially calm: no agency arrests anyone on a video call. \
Do not use countdown pressure on them.
- You are independent and free. You are not RBI, the Government, the police, NCRP or their bank. \
This is legal information, not legal advice.

How to work:
- Reply in the user's language (English or Hindi, matching how they write).
- Interview briefly: what happened, each debit (amount, date-time), whether an alert SMS arrived, \
whether they shared an OTP or installed an app, whether they were threatened, and when they \
reported to the bank and to 1930. One or two questions at a time.
- Every rupee amount, liability outcome and date must come from a tool: classify_case, \
compute_entitlement, deadline_calendar. Never compute or guess these yourself. Pass dates in ISO \
format. Set only the answers the user confirmed.
- Explain results plainly with the paragraph cited (for example "76N", "2017 para 6(ii)"). Present \
classifications as candidates: the bank decides and must prove the customer's liability.
- State only rules, paragraphs, entitlements, conditions and deadlines that appear in tool results. \
Do not add others from memory: no provisional or shadow credit, refund timelines or "angles" unless \
a tool returned them, and do not explain why a cap or rule exists beyond what the tool says. If the \
user asks about something the tools do not cover, say you cannot confirm it and suggest they ask \
the bank or the RBI Ombudsman.
- If several causes apply, show each. If a tool returns an error, ask for the missing fact. If an \
answer would change the result (for example whether an SMS alert arrived), ask it and re-run the tool.
- Mention that rules were last verified on the date the tools return.
- Keep the tone plain and calm: short paragraphs or a small table, no emojis, no alarm words.
"""

_GATEWAY_URL = os.environ.get("AGENTCORE_GATEWAY_TOOLS_URL")
_gateway = (
    MCPClient(lambda: aws_iam_streamablehttp_client(
        endpoint=_GATEWAY_URL + "/mcp",
        aws_region=os.environ.get("AWS_REGION", "us-east-1"),
        aws_service="bedrock-agentcore",
    ))
    if _GATEWAY_URL else None
)


def _redact_prompt(prompt):
    """Strip secrets from user text before the model sees it."""
    if isinstance(prompt, str):
        return redact_message(prompt)
    redacted, kinds = [], []
    for message in prompt:
        content = []
        for block in message.get("content", []):
            if message.get("role") == "user" and isinstance(block.get("text"), str):
                text, found = redact_message(block["text"])
                kinds += found
                block = {**block, "text": text}
            content.append(block)
        redacted.append({**message, "content": content})
    return redacted, kinds


@lru_cache(maxsize=128)
def _get_agent(session_id: str, actor_id: str) -> Agent:
    return Agent(
        model=load_model(),
        session_manager=get_memory_session_manager(session_id, actor_id),
        conversation_manager=NullConversationManager(),
        system_prompt=SYSTEM_PROMPT,
        tools=[_gateway] if _gateway else [],
    )


def create_app():
    app = BedrockAgentCoreApp()
    log = app.logger

    @app.entrypoint
    async def invoke(payload, context):
        session_id = getattr(context, "session_id", None) or "default-session"
        prompt, actor_id = parse_payload(payload)
        prompt, removed = _redact_prompt(prompt)
        if removed:
            log.info("redacted from user input: %s", sorted(set(removed)))
        agent = _get_agent(session_id, actor_id)

        async for event in agent.stream_async(prompt):
            if not isinstance(event, dict) or "event" not in event:
                continue
            cbs = event["event"].get("contentBlockStart")
            if cbs is not None and not cbs.get("start"):
                continue
            yield event

    return app


app = create_app()
if __name__ == "__main__":
    app.run()
