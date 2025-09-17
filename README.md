# 🎵 SuperMusic

SuperMusic is a Python-based pipeline and web app for **downloading, processing, enriching, and visualizing music data**.  
It automates audio downloads, stem separation, transcription, metadata enrichment, and interactive 3-D visualizations.

---

## 🚀 Features
- **Audio Downloads** from YouTube or other sources
- **Stem Separation** (vocals, drums, bass, etc.)
- **Transcription** to MIDI or note events
- **Metadata Enrichment** from external APIs & datasets
- **3-D Visualizations** (UMAP, Plotly) for music similarity
- **Interactive Web App** built with FastAPI + Jinja2 templates

---

## 📂 Project Structure
```
supermusic/
├── supermusic/            # Main Python package
│   ├── cli/               # CLI entry points
│   ├── core/              # Core pipeline modules
│   ├── web/               # Web application
│   └── utils/             # Small helpers
├── tests/                 # Unit and integration tests
├── docs/                  # Project documentation
└── .github/workflows/     # CI/CD configuration
```

---

## 🛠️ Installation
Clone the repo and install dependencies:

```bash
git clone https://github.com/yourname/supermusic.git
cd supermusic
pip install -r requirements.txt
```

Optional: install via `pyproject.toml`:

```bash
pip install .
```

---

## 💻 Command-Line Usage
```bash
# Download audio
supermusic download https://youtube.com/...

# Separate stems
supermusic separate my_song.mp3
```

---

## 🌐 Web Interface
Start the FastAPI app:

```bash
uvicorn supermusic.web.app:app --reload
```

Open [http://localhost:8000](http://localhost:8000) to view the dashboard.

---

## 🧪 Testing
```bash
pytest
```

---

## 📚 Documentation
- [API Reference](docs/api.md)
- [Usage Guide](docs/usage.md)

---

## 🤝 Contributing
1. Fork the repository.
2. Create a feature branch.
3. Add tests and documentation.
4. Submit a pull request.

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).

---

*Built with ❤️ by Agang Dut.* 