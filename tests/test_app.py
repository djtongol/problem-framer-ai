"""End-to-end tests of app.py with Streamlit's AppTest and a fake model (no API calls)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

from conftest import read_fixture

APP = str(Path(__file__).resolve().parent.parent / "app.py")
GOOD_BRIEF = read_fixture("good_brief")


def make_app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.secrets["PROVIDER"] = "openai"
    at.secrets["OPENAI_API_KEY"] = "test-key"
    at.secrets["ACCESS_CODE"] = "letmein"
    return at


def start(at: AppTest, code: str = "letmein") -> AppTest:
    at.run()
    at.sidebar.text_input[0].input(code).run()
    return at


def send(at: AppTest, text: str) -> AppTest:
    at.chat_input[0].set_value(text).run()
    return at


def all_markdown(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_happy_path_hides_the_status_line(use_fake_model):
    model = use_fake_model([read_fixture("good_clarify")])
    at = send(start(make_app()), "Our support tickets are taking too long to close.")
    assert not at.exception and not at.error
    assert len(model.calls) == 1 and len(at.chat_message) == 2
    shown = at.chat_message[1].markdown[0].value
    assert "CLARIFICATION NEEDED" in shown and "STATUS:" not in shown


def test_no_access_code_secret_hides_the_box_and_just_works(use_fake_model):
    model = use_fake_model([read_fixture("good_clarify")])
    at = AppTest.from_file(APP, default_timeout=30)
    at.secrets["PROVIDER"] = "openai"
    at.secrets["OPENAI_API_KEY"] = "test-key"
    at.run()
    assert len(at.sidebar.text_input) == 0
    send(at, "Our support tickets are taking too long to close.")
    assert not at.exception and not at.error and len(model.calls) == 1


def test_wrong_access_code_blocks_the_call(use_fake_model):
    model = use_fake_model([read_fixture("good_clarify")])
    at = send(start(make_app(), code="wrong"), "hello there")
    assert at.error and "Access code" in at.error[0].value
    assert model.calls == []


def test_overlong_message_is_rejected_without_an_api_call(use_fake_model):
    model = use_fake_model([read_fixture("good_clarify")])
    at = send(start(make_app()), "x" * 5000)
    assert at.error and "5,000" in at.error[0].value
    assert model.calls == []


def test_brief_reply_shows_info_and_downloads(use_fake_model):
    use_fake_model([GOOD_BRIEF])
    at = send(start(make_app()), "Everything in one message")
    assert not at.exception
    assert any("Review the Open Questions" in i.value for i in at.info)
    labels = [d.proto.label for d in at.get("download_button")]
    assert labels == ["Download Word document", "Download Markdown"]
    assert "STATUS:" not in all_markdown(at)


def test_unparseable_brief_still_offers_markdown(use_fake_model, monkeypatch):
    use_fake_model([GOOD_BRIEF])
    def explode(brief):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.export_docx.brief_to_docx", explode)  # app.py imports it on every run
    at = send(start(make_app()), "Everything in one message")
    assert not at.exception
    assert any("could not build the Word document" in w.value for w in at.warning)
    assert [d.proto.label for d in at.get("download_button")] == ["Download Markdown"]


def test_option_button_sends_the_choice_as_the_next_message(use_fake_model):
    model = use_fake_model([read_fixture("guidance_clarify"), read_fixture("good_clarify")])
    at = send(start(make_app()), "I'm not sure")
    options = [b for b in at.button if b.label.startswith(("A)", "B)", "C)"))]
    assert [b.label[:2] for b in options] == ["A)", "B)", "C)"]
    options[0].click().run()
    assert len(model.calls) == 2
    assert model.calls[1][-1].content == "A) Median hours from ticket opened to closed"
    assert not at.exception


def test_turn_limit_disables_the_input(use_fake_model):
    use_fake_model([])
    at = make_app()
    at.session_state["messages"] = [
        {"role": r, "content": "x" if r == "user" else read_fixture("good_clarify")}
        for _ in range(12) for r in ("user", "assistant")]
    at.run()
    assert at.chat_input[0].disabled
    assert any("limit of 12" in i.value for i in at.info)


def test_badly_formatted_reply_shows_a_warning(use_fake_model):
    use_fake_model(["no status line", "still none"])
    at = send(start(make_app()), "hello there")
    assert any("may not follow the expected format" in w.value for w in at.warning)


def test_start_new_conversation_clears_the_chat(use_fake_model):
    use_fake_model([read_fixture("good_clarify")])
    at = send(start(make_app()), "hello there")
    assert len(at.chat_message) == 2
    next(b for b in at.sidebar.button if b.label == "Start new conversation").click().run()
    assert len(at.chat_message) == 0
