"""Show which models your keys can really use, and test the ones in secrets.toml.
 
Run from the project folder:  python check_models.py
Secret values are never printed.
"""
import tomllib
from pathlib import Path
 
import requests
 
SECRETS = Path(".streamlit/secrets.toml")
TIMEOUT = 30
DEFAULTS = {"openai": ("gpt-4.1-mini", "gpt-4.1-nano"),
            "google": ("gemini-2.5-flash", "gemini-2.5-flash-lite")}
 
 
def clip(text: str, n: int = 200) -> str:
    return " ".join(str(text).split())[:n]
 
 
def google_models(key: str) -> list[str]:
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=TIMEOUT)
    r.raise_for_status()
    return sorted(m["name"].removeprefix("models/") for m in r.json().get("models", [])
                  if "generateContent" in m.get("supportedGenerationMethods", []))
 
 
def openai_models(key: str) -> list[str]:
    r = requests.get("https://api.openai.com/v1/models",
                     headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    r.raise_for_status()
    skip = ("embedding", "tts", "whisper", "image", "audio", "realtime", "transcribe",
            "moderation", "dall-e", "search", "codex", "instruct")
    return sorted(m["id"] for m in r.json().get("data", [])
                  if m["id"].startswith(("gpt-", "o1", "o3", "o4"))
                  and not any(s in m["id"] for s in skip))
 
 
def test_google(key: str, model: str) -> str:
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      headers={"x-goog-api-key": key},
                      json={"contents": [{"parts": [{"text": "Say OK"}]}]}, timeout=TIMEOUT)
    return "WORKS" if r.ok else f"FAILED (HTTP {r.status_code}): {clip(r.json().get('error', {}).get('message', r.text))}"
 
 
def test_openai(key: str, model: str) -> str:
    r = requests.post("https://api.openai.com/v1/chat/completions",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": model, "messages": [{"role": "user", "content": "Say OK"}],
                            "max_completion_tokens": 50}, timeout=TIMEOUT)
    return "WORKS" if r.ok else f"FAILED (HTTP {r.status_code}): {clip(r.json().get('error', {}).get('message', r.text))}"
 
 
def main() -> None:
    secrets = tomllib.loads(SECRETS.read_text(encoding="utf-8"))
    provider = str(secrets.get("PROVIDER", "openai")).strip().lower()
    print(f"PROVIDER in secrets: {provider}")
    if provider not in DEFAULTS:
        print("PROVIDER must be 'openai' or 'google'.")
        return
    main_model = str(secrets.get("MODEL_NAME") or DEFAULTS[provider][0])
    fast_model = str(secrets.get("FAST_MODEL_NAME") or DEFAULTS[provider][1])
    print(f"MODEL_NAME: {main_model}\nFAST_MODEL_NAME: {fast_model}\n")
 
    if provider == "google":
        key = secrets.get("GOOGLE_API_KEY") or secrets.get("GEMINI_API_KEY")
        lister, tester = google_models, test_google
    else:
        key = secrets.get("OPENAI_API_KEY")
        lister, tester = openai_models, test_openai
    if not key:
        print("No key found for this provider in secrets.toml.")
        return
 
    available = lister(key)
    print(f"Models your key can use ({len(available)}):")
    for name in available:
        print(f"  {name}")
    print()
    for label, name in (("MODEL_NAME", main_model), ("FAST_MODEL_NAME", fast_model)):
        listed = "listed" if name in available else "NOT in your list"
        print(f"{label} = {name}: {listed}; test call: {tester(key, name)}")
 
 
main()
 

