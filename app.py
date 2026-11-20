"""Problem Framer AI: a chat that interviews you and writes a Business Requirements Brief."""

from __future__ import annotations

import datetime
import re

import streamlit as st

from src.brief_parser import parse_brief
from src.chain import ChainError, parse_status, run_turn
from src.config import MAX_MESSAGE_CHARS, AccessDenied, get_settings
from src.export_docx import brief_to_docx
from src.ui_helpers import (escape_dollars, extract_options, format_for_display, progress_text,
                            render_option_buttons, render_sidebar_legend, strip_status_line)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DEFAULT_MAX_TURNS = 12
PRIVACY = ("Do not paste confidential or personal data. Your text is sent to the AI provider's API. "
           "This app does not store conversations.")

st.set_page_config(page_title="Problem Framer AI")


def reset_chat() -> None:
    """Clear the conversation (the sidebar key and code stay)."""
    for key in ("messages", "queued_input"):
        st.session_state.pop(key, None)


def resolve_settings():
    """Return (settings, error_message); the error is shown only when a turn is attempted."""
    try:
        return get_settings(), ""
    except AccessDenied as exc:
        return None, str(exc)
    except Exception:  # e.g. secrets.toml missing
        return None, "Could not read the settings. Check .streamlit/secrets.toml."


def brief_downloads(text: str, index: int) -> None:
    """Word and Markdown download buttons for a BRIEF reply."""
    docx_bytes, title = None, ""
    try:
        brief = parse_brief(text)
        title = brief.title
        docx_bytes = brief_to_docx(brief)
    except Exception:
        st.warning("I could not build the Word document from this brief. You can still download the Markdown.")
    name = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "business-requirements-brief"
    cols = st.columns(2)
    if docx_bytes:
        cols[0].download_button("Download Word document", docx_bytes, file_name=f"{name}.docx",
                                mime=DOCX_MIME, key=f"dl_docx_{index}")
    cols[1].download_button("Download Markdown", strip_status_line(text), file_name=f"{name}.md",
                            mime="text/markdown", key=f"dl_md_{index}")


def show_message(msg: dict, index: int, is_last: bool, at_limit: bool) -> None:
    """Draw one chat message; the latest assistant message also gets buttons and downloads."""
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(escape_dollars(msg["content"]))
            return
        status = parse_status(msg["content"])
        body = strip_status_line(msg["content"])
        if status == "BRIEF":
            with st.container(border=True):
                st.markdown(format_for_display(body))
            if is_last:
                st.info("Review the Open Questions section, then reply with any corrections "
                        "and I will regenerate the brief.")
                brief_downloads(msg["content"], index)
        else:
            st.markdown(format_for_display(body))
        if msg.get("problems"):
            st.warning("This reply may not follow the expected format. Treat it with care.")
        if is_last and status == "CLARIFY" and not at_limit:
            render_option_buttons(extract_options(msg["content"]), f"opt_{index}")


def handle_turn(text: str, settings, settings_error: str) -> None:
    """Validate the input, call the model, store the exchange and rerun."""
    if len(text) > MAX_MESSAGE_CHARS:
        st.error(f"That message has {len(text):,} characters. Please shorten it to {MAX_MESSAGE_CHARS:,} "
                 "or fewer and send it again. It was not sent.")
        return
    if settings is None:
        st.error(f"{settings_error} Your message was not sent.")
        return
    messages = st.session_state.messages
    history = [{"role": m["role"], "content": m["content"]} for m in messages]
    history.append({"role": "user", "content": text})
    progress = st.progress(0, text="Starting 0%")

    def on_stage(percent: int, label: str) -> None:
        progress.progress(percent, text=f"{label}... {percent}%")

    try:
        result = run_turn(history, settings, datetime.date.today().isoformat(), on_stage)
    except (AccessDenied, ChainError) as exc:
        progress.empty()
        st.error(f"{exc} Your message was not sent.")
        return
    progress.empty()
    messages.append({"role": "user", "content": text})
    messages.append({"role": "assistant", "content": result.text, "problems": result.problems})
    st.rerun()


def main() -> None:
    st.title("Problem Framer AI")
    st.write("Describe your business problem. I will ask a few questions, then write a Business Requirements Brief.")
    st.sidebar.button("Start new conversation", on_click=reset_chat)
    settings, settings_error = resolve_settings()
    limit = settings.max_user_turns if settings else DEFAULT_MAX_TURNS

    messages = st.session_state.setdefault("messages", [])
    user_count = sum(1 for m in messages if m["role"] == "user")
    at_limit = user_count >= limit
    st.sidebar.write(progress_text(user_count, limit))
    render_sidebar_legend()
    st.sidebar.info(PRIVACY)

    queued = st.session_state.pop("queued_input", None)
    for i, msg in enumerate(messages):
        show_message(msg, i, i == len(messages) - 1, at_limit)
    if at_limit:
        st.info(f"You reached the limit of {limit} messages for one conversation. "
                "Click 'Start new conversation' in the sidebar to continue.")
    prompt = st.chat_input("Describe your business problem...", disabled=at_limit)
    text = prompt or queued
    if text and not at_limit:
        with st.chat_message("user"):
            st.markdown(escape_dollars(text))
        handle_turn(text, settings, settings_error)
    st.caption("Experimental tool. Verify all outputs before sharing.")


main()
