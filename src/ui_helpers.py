"""Small Streamlit display helpers: colored tags, option buttons, progress, legend."""

from __future__ import annotations

import re

import streamlit as st

_OPTION = re.compile(r"^\s*([A-D])\)\s+(.+?)\s*$")


def render_tags(text: str) -> str:
    """Show [Stated] in green and [Suggested] in orange using Streamlit colored text."""
    return text.replace("[Stated]", ":green[Stated]").replace("[Suggested]", ":orange[Suggested]")


def strip_status_line(reply: str) -> str:
    """Remove the STATUS line (and blank lines after it) before showing a reply."""
    lines = reply.splitlines()
    if lines and lines[0].strip().startswith("STATUS:"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def escape_dollars(text: str) -> str:
    """Stop Streamlit from reading $...$ as math."""
    return text.replace("$", "\\$")


def format_for_display(text: str) -> str:
    """Escape $, keep single line breaks visible, and color the provenance tags."""
    return render_tags(escape_dollars(text)).replace("\n", "  \n")


def extract_options(reply: str) -> list[tuple[str, str]]:
    """Return (letter, text) for lettered options A) to D), leaving out 'None of these'."""
    options = []
    for line in reply.splitlines():
        m = _OPTION.match(line)
        if m and not m.group(2).lower().startswith("none of these"):
            options.append((m.group(1), m.group(2)))
    return options


def _queue(text: str) -> None:
    st.session_state["queued_input"] = text


def render_option_buttons(options: list[tuple[str, str]], key_prefix: str) -> None:
    """One button per option; a click queues 'A) option text' as the next user message."""
    if not options:
        return
    for i, (letter, text) in enumerate(options):
        st.button(f"{letter}) {text}", key=f"{key_prefix}_{i}", on_click=_queue, args=(f"{letter}) {text}",))
    st.caption("None of these? Type your own answer below.")


def progress_text(user_count: int, max_turns: int) -> str:
    """Text for the sidebar progress indicator."""
    return f"Turn {user_count} of {max_turns}"


def render_sidebar_legend() -> None:
    """Explain the provenance tags in the sidebar."""
    st.sidebar.caption(":green[Stated] = you told me. :orange[Suggested] = I proposed it; please confirm.")
