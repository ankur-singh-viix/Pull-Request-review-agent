try:  # load a local .env if python-dotenv is installed (real env vars still win)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass