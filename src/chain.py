"""LLM chain: build the system prompt, call the model, validate, retry once."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.config import Settings
from src.reference_loader import build_reference_context
from src.validators import validate_reply

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.md"
TEMPERATURE = 0.2


class ChainError(Exception):
    """A model call failed. The message is short, friendly and never contains a key."""


@dataclass
class TurnResult:
    """One assistant turn: the reply text, its status, format problems, retry flag."""

    text: str
    status: str
    problems: list[str] = field(default_factory=list)
    retried: bool = False


@lru_cache(maxsize=1)
def load_system_prompt() -> str:
    """Read prompts/system_prompt.md once and cache it."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_system_prompt(user_texts: list[str], today: str) -> str:
    """Fill the four prompt variables using plain str.replace."""
    ctx = build_reference_context(" ".join(user_texts))
    values = {
        "{current_date}": today,
        "{metrics_reference}": ctx["metrics_reference"],
        "{decisions_reference}": ctx["decisions_reference"],
        "{lens_reference}": ctx["lens_reference"],
    }
    prompt = load_system_prompt()
    for placeholder, value in values.items():
        prompt = prompt.replace(placeholder, value.strip() or "(none)")
    return prompt


def parse_status(reply: str) -> str:
    """Return CLARIFY, BRIEF or CHAT from the first line, else UNKNOWN."""
    first = reply.splitlines()[0].strip() if reply.strip() else ""
    for status in ("CLARIFY", "BRIEF", "CHAT"):
        if first == f"STATUS: {status}":
            return status
    return "UNKNOWN"


def _supports_temperature(model_name: str) -> bool:
    """OpenAI reasoning models (gpt-5, o-series) reject a custom temperature."""
    name = model_name.lower()
    return not (name.startswith("gpt-5") or name[:2] in ("o1", "o3", "o4"))


def _get_model(settings: Settings, model_name: str | None = None) -> Any:
    """Create the chat model for the configured provider (imports are lazy)."""
    name = model_name or settings.model_name
    tokens = settings.max_output_tokens
    try:
        if settings.provider == "openai":
            from langchain_openai import ChatOpenAI

            kwargs: dict[str, Any] = {"model": name, "api_key": settings.api_key, "max_tokens": tokens}
            if _supports_temperature(name):
                kwargs["temperature"] = TEMPERATURE
            return ChatOpenAI(**kwargs)
        if settings.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI

            # Gemini counts its "thinking" tokens against the output limit, so give it headroom.
            return ChatGoogleGenerativeAI(
                model=name, api_key=settings.api_key, temperature=TEMPERATURE,
                max_output_tokens=tokens * 2,
            )
    except ImportError as exc:
        pkg = {"openai": "langchain-openai", "google": "langchain-google-genai"}.get(
            settings.provider, "the provider package")
        raise ChainError(f"The package for provider '{settings.provider}' is missing. Run: pip install {pkg}") from exc
    raise ChainError(f"Unknown provider '{settings.provider}'.")


def _content_text(content: Any) -> str:
    """Flatten a model reply (a string, or a list of content blocks) into plain text."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type", "text") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def _friendly_error(exc: Exception) -> str:
    """Map a provider exception to a short message without echoing its text."""
    names = " ".join(c.__name__ for c in type(exc).__mro__).lower()
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    text = str(exc).lower()
    if code in (401, 403) or any(k in names for k in ("authentication", "permissiondenied", "unauthorized")) \
            or "api key not valid" in text or "api_key_invalid" in text:
        return "The API key was rejected or does not have access. Check the key."
    if code == 404 or "notfound" in names or "model not found" in text:
        return "The model name was not found for this provider. Check MODEL_NAME in your secrets."
    if code == 429 or any(k in names for k in ("ratelimit", "resourceexhausted")) or "quota" in text:
        return "The provider is rate limiting or out of quota. Wait a moment and try again."
    if any(k in names for k in ("connection", "timeout", "unavailable", "network")) or code in (500, 502, 503, 504):
        return "Could not reach the model service. Check your connection and try again."
    return f"The model call failed ({type(exc).__name__}). Please try again."


def _call(model: Any, system_prompt: str, history: list[dict]) -> str:
    """Send the system prompt plus history and return the reply text."""
    messages: list[Any] = [SystemMessage(content=system_prompt)]
    for m in history:
        cls = HumanMessage if m["role"] == "user" else AIMessage
        messages.append(cls(content=m["content"]))
    try:
        response = model.invoke(messages)
    except Exception as exc:  # provider SDKs raise many different types
        raise ChainError(_friendly_error(exc)) from None
    text = _content_text(response.content).strip()
    if not text:
        raise ChainError("The model returned an empty reply (it may have run out of output tokens). Please try again.")
    return text


def _retry_message(problems: list[str]) -> str:
    listed = "\n".join(f"- {p}" for p in problems)
    return ("Your reply had these format problems:\n" + listed +
            "\nRewrite the full reply and fix only these problems. Keep the same facts.")


def run_turn(history: list[dict], settings: Settings, today: str, on_stage=None) -> TurnResult:
    """Run one assistant turn. history is a list of {"role": "user"|"assistant", "content": str}.

    on_stage(percent, label) is called as the turn moves through its stages.
    """
    def stage(percent: int, label: str) -> None:
        if on_stage:
            on_stage(percent, label)

    stage(10, "Preparing your request")
    user_texts = [m["content"] for m in history if m["role"] == "user"]
    system_prompt = build_system_prompt(user_texts, today)
    model = _get_model(settings)
    stage(30, "Waiting for the model (this is the slow part)")
    text = _call(model, system_prompt, history)
    stage(75, "Checking the reply format")
    problems = validate_reply(text)
    if not problems:
        stage(100, "Done")
        return TurnResult(text, parse_status(text))
    stage(80, "Fixing format problems")
    retry_history = history + [
        {"role": "assistant", "content": text},
        {"role": "user", "content": _retry_message(problems)},
    ]
    try:
        text2 = _call(model, system_prompt, retry_history)
    except ChainError:
        return TurnResult(text, parse_status(text), problems, False)
    stage(100, "Done")
    return TurnResult(text2, parse_status(text2), validate_reply(text2), True)