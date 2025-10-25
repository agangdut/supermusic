# Justfile for SuperMusic
# Run commands with: just <task>

# Install dependencies from requirements.txt
install:
    pip install -r requirements.txt

# Run the CLI entry point
run:
    python -m supermusic.cli.main

# Run the web server (FastAPI)
run-web:
    uvicorn supermusic.web.app:app --reload

# Run tests
test:
    pytest tests

# Format code with black (optional, install black first)
format:
    black supermusic tests

# Lint with ruff (optional, install ruff first)
lint:
    ruff check supermusic tests
