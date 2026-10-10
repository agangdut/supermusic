# --- cross-platform shell config --------------------------------------------
# Use PowerShell on Windows, bash elsewhere
set shell := ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]

# --- tool paths --------------------------------------------------------------
py      := "py"
python  := ".venv\\Scripts\\python.exe"
pip     := ".venv\\Scripts\\pip.exe"
pre     := ".venv\\Scripts\\pre-commit.exe"
ruff    := ".venv\\Scripts\\ruff.exe"
pytest  := ".venv\\Scripts\\pytest.exe"

# cross-platform "rm -rf"
RMRF    := "Remove-Item -Recurse -Force"

# --- default/help ------------------------------------------------------------
default:
  @just --list

help:
  @echo "Common tasks:"
  @echo "  just setup        # create venv and install deps"
  @echo "  just lint         # ruff + format"
  @echo "  just test         # run pytest"
  @echo "  just run path=... # analyze a track"
  @echo "  just separate path=... [engine=demucs]"
  @echo "  just transcribe path=..."
  @echo "  just report path=... out=artifacts/report.html"
  @echo "  just clean        # remove caches/build/interim data"

# --- environment/bootstrap ---------------------------------------------------
setup:
  {{py}} -m venv .venv
  {{python}} -m pip install -U pip wheel
  {{pip}} install -e ".[dev,separation,transcription]"
  {{pre}} install

lint:
  {{ruff}} check .
  {{ruff}} format .

# Use Just's '-' to ignore non-zero exit codes (portable)
typecheck:
  - {{python}} -m mypy src

test *ARGS:
  {{pytest}} -q {{ARGS}}

# --- project commands --------------------------------------------------------
# Example CLI hooks; adjust to your actual Typer/CLI entry points.
run path:
  {{python}} -m supermusic.cli analyze "{{path}}"

separate path engine="demucs":
  {{python}} -m supermusic.cli separate --engine "{{engine}}" "{{path}}"

transcribe path:
  {{python}} -m supermusic.cli transcribe "{{path}}"

report path out="artifacts/report.html":
  {{python}} -m supermusic.cli report --track "{{path}}" --out "{{out}}"

# Batch process everything in a folder (Windows PowerShell)
# Batch process everything in a folder (Windows PowerShell)
batch-separate dir engine="demucs":
  $exts=@("*.mp3","*.wav","*.flac","*.m4a","*.aac"); $files=Get-ChildItem -Recurse "{{dir}}" -Include $exts -File; foreach ($f in $files) { {{python}} -m supermusic.cli separate --engine "{{engine}}" "$($f.FullName)" }

# --- cleaning & packaging ----------------------------------------------------
# PowerShell-safe cleaner (no bash globs)
clean:
  clean:
  $paths=@("dist","build",".mypy_cache",".ruff_cache","data\\interim\\separated","artifacts"); foreach ($p in $paths) { if (Test-Path $p) { Remove-Item -Recurse -Force $p } }; Get-ChildItem -Recurse -Directory -Filter "__pycache__" | ForEach-Object { Remove-Item -Recurse -Force $_.FullName }

build:
  {{python}} -m pip install build
  {{python}} -m build

# quick formatter for this justfile itself
fmt:
  just --fmt
