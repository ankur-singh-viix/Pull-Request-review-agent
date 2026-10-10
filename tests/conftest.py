import os

# Tests must never hit a real LLM or GitHub, even if a local .env has real keys.
os.environ["USE_FAKE_LLM"] = "1"
os.environ["DRY_RUN"] = "1"