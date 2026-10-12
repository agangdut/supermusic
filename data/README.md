# data/

Everything the app reads and writes at runtime lives here. Docker mounts this folder into the containers, so files survive a restart. **Nothing in it is committed** (see `.gitignore`), apart from this file.

| Folder | What goes in it |
|---|---|
| `raw/` | Your uploads, downloaded songs and benchmark datasets (MAESTRO, MusicNet, MulTTiPop) |
| `interim/` | Working files: separated stems, cut clips |
| `processed/` | Results: MIDI, stems, enriched CSVs, Music Map libraries, benchmark scores |
| `artifacts/` | Files the web app offers as downloads |
| `models/` | Model weights, downloaded on first use (Hugging Face cache in `models/hf`) |
| `cache/` | Lookups that are slow to repeat, such as genre tags and preview embeddings |
