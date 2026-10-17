"""Create (once) and update the SuperMusic API Space. Run by .github/workflows/hf-space.yml.

Needs HF_TOKEN (a write token). CORS_ORIGINS is set to the GitHub Pages site.
"""
import os
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
api = HfApi(token=os.environ["HF_TOKEN"])
user = api.whoami()["name"]
space = f"{user}/{os.getenv('HF_SPACE_NAME', 'supermusic')}"

new = not api.repo_exists(space, repo_type="space")
if new:
    api.create_repo(space, repo_type="space", space_sdk="docker")
    # Signs login tokens; set once so a redeploy doesn't sign everyone out
    api.add_space_secret(space, "JWT_SECRET_KEY", secrets.token_hex(32))
api.add_space_variable(space, "CORS_ORIGINS", os.getenv("CORS_ORIGINS", "https://agangdut.github.io"))

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp)
    for name in ("Dockerfile", "README.md"):
        shutil.copy(ROOT / "deploy/hf-space" / name, out / name)
    shutil.copy(ROOT / "requirements.txt", out / "requirements.txt")
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "tests")
    shutil.copytree(ROOT / "backend", out / "backend", ignore=ignore)
    shutil.copytree(ROOT / "scripts", out / "scripts", ignore=ignore)
    api.upload_folder(folder_path=out, repo_id=space, repo_type="space",
                      commit_message=f"Deploy {os.getenv('GITHUB_SHA', 'local')[:7]}", delete_patterns="*")

host = space.replace("/", "-").replace("_", "-").lower()
print(f"{'Created' if new else 'Updated'} https://huggingface.co/spaces/{space} (API at https://{host}.hf.space)")
sys.stdout.flush()
