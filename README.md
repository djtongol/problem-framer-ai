 Problem Framer AI

A Streamlit chat app that interviews you about a business problem and writes a **Business Requirements Brief**.
It asks up to four questions per turn, guides you with options when you are unsure, tags every fact as
Stated (you said it) or Suggested (the AI proposed it), and exports the brief as a Word document or Markdown.

Built with LangChain (OpenAI or Gemini), pandas and python-docx. Deploys on the free Streamlit Community Cloud tier.

## Run locally

1. Python 3.11 or 3.12. Create and activate a virtual environment, then `pip install -r requirements.txt`.
2. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`. Set `PROVIDER` (`openai` is the default, or `google`),
   the matching key (`OPENAI_API_KEY`, or `GOOGLE_API_KEY` / `GEMINI_API_KEY`) and an `ACCESS_CODE`.
   Optional: `MODEL_NAME` and `FAST_MODEL_NAME`.
3. `streamlit run app.py`, then type the access code in the sidebar.
4. Run the tests with `pytest -q`. They never call a real model.

## Folder structure

```
app.py                     Streamlit chat page
prompts/system_prompt.md   The full system prompt (edit wording here, not in Python)
data/                      metrics.csv, decisions.csv, diagnostic_lens.csv (reference data)
src/config.py              Settings from secrets, provider choice
src/reference_loader.py    CSV loading and keyword retrieval
src/chain.py               Prompt building, model call, validation, one automatic retry
src/validators.py          Format checks on every reply
src/brief_parser.py        Brief text to Python objects
src/export_docx.py         Word export
src/ui_helpers.py          Colored tags, option buttons, progress, legend
tests/                     pytest tests (fake model, no API calls)
docs/MANUAL_TESTS.md       The 8 live scenarios to run before sharing
docs/CHANGELOG.md          Reference data notes and column descriptions
```

## Deploy (Streamlit Community Cloud)

1. Push the repo to GitHub. Check that `.streamlit/secrets.toml` is NOT in it.
2. On share.streamlit.io click New app, pick the repo, branch `main`, main file `app.py`, Python 3.11 or 3.12.
3. In Advanced settings, paste the contents of your local `secrets.toml` into the Secrets box. Deploy.
4. To update, commit and push. The app redeploys itself.

## Add a new metric

Edit `data/metrics.csv` and add one row. Columns are explained in `docs/CHANGELOG.md`. Give each metric a unique
`metric_id`, add the words your users say to the `aliases` column (separated by `;`), and leave `duplicate_of` empty.
Run `pytest -q`: the loader tests check the row count and the search results.

## Notes

- Experimental tool. Verify all outputs before sharing.
- Do not paste confidential or personal data: your text is sent to the AI provider. The app does not store conversations.
- Limits: 12 user messages per conversation and 4,000 characters per message.
