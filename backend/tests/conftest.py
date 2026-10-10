import os
import sys
import tempfile
from pathlib import Path

# The app imports itself as "app.*", so backend/ has to be on the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep test uploads and artifacts out of the real data folder.
_tmp = Path(tempfile.mkdtemp(prefix="supermusic-tests-"))
os.environ["SM_DATA_DIR"] = str(_tmp / "data")
os.environ["SM_RAW_DIR"] = str(_tmp / "data" / "raw")
os.environ["SUPERMUSIC_ARTIFACT_DIR"] = str(_tmp / "artifacts")
