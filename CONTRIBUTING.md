# Contributing to JARVIS MK-X

First off, thank you for considering contributing to **JARVIS MK-X**! It's people like you who make JARVIS a great autonomous engineering agent.

---

## 🛠️ Code of Conduct

This project follows the standard Contributor Covenant Code of Conduct. Please be respectful and considerate in your interactions.

---

## 🚀 Getting Started & Local Development

### 1. Prerequisites
- **Python 3.11+**
- Git

### 2. Fork & Clone
```bash
git clone https://github.com/YOUR_USERNAME/JARVIS.git
cd JARVIS
```

### 3. Environment Setup
```bash
# Create virtual environment
python -m venv venv

# Activate (Windows PowerShell / cmd)
.\venv\Scripts\Activate.ps1
# or on Linux/macOS: source venv/bin/activate

# Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pytest ruff
```

### 4. Running the Agent
```bash
# Launch interactive terminal
python -m cli

# One-shot command execution
python -m cli "inspect repository"
```

---

## 🧪 Testing & Code Quality

Before submitting a Pull Request, please ensure all checks pass:

```bash
# 1. Run quick safety lint checks
ruff check . --select E9,F63,F7,F82

# 2. Run the test suite
pytest tests/ -q

# 3. Verify the performance gate
python -m benchmark.gate --baseline benchmark/baseline.json --ci
```

---

## 📦 Pull Request Guidelines

1. **Branch Naming**: Use descriptive branch names (e.g. `feat/mcp-connector`, `fix/provider-fallback`).
2. **Atomic Commits**: Keep commits focused and logically grouped with descriptive messages.
3. **Tests**: Add unit or integration tests in `tests/` for new functionality.
4. **Documentation**: Update `README.md` or files under `docs/` when introducing user-facing changes or flags.
5. **PR Description**: Include a clear summary of what changes were made, why, and how they were tested.

---

## 💡 Reporting Bugs & Requesting Features

- Use GitHub Issues to file bugs or feature requests.
- Provide full logs, Python version, OS environment, and exact CLI commands when reporting bugs.
