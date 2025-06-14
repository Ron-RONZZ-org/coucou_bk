# Coucou 🗣️

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://python.org)
[![Qt6](https://img.shields.io/badge/Qt-6-green.svg)](https://qt.io)
[![PySide6](https://img.shields.io/badge/PySide-6-orange.svg)](https://pyside.org)
[![License](https://img.shields.io/badge/License-Open%20Source-brightgreen.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Alpha-yellow.svg)]()

> ❗ **Language Notice**: Although all core functionalities, including TTS, work for most languages, Coucou's interface and conjugator are currently French only. I began developing this app for personal use and made this choice for my personal convenience while learning French. UI translation efforts are warmly welcomed.

Coucou is a multi-platform minimalist FOSS wordbank for language learning based on the Qt6 PySide framework.

## ✨ Key Features

- **📥 Vocabulary Import** - Import media-rich vocabulary/key phrase lists
- **🔊 Automatic TTS** - Automatically generate audio with Google TTS
- **📝 Custom Review** - Review/test a custom range of saved vocabularies
  - Filter by date
  - Mark favorites
- **💾 Progress Backup** - Export and restore progress of a review session
- **🔍 Search & Edit** - Search for and edit saved vocabularies
- **🇫🇷 French Conjugator** - A French verb conjugator (conjugateur pour les verbes français)

## 🚀 Advantages

### Run Anywhere
Coucou is based on PySide 6 and can therefore be compiled to run on:
- **Desktop**: Linux family systems, Windows, macOS
- **Mobile**: Ubuntu Touch, Android, iOS

### Minimalist Interface
Coucou's minimalist and self-intuitive interface directs your attention to the language you are trying to learn.

## 📊 Project Status

### 🟡 Alpha
- ✅ **All main functionalities work**
- ❗ **No build version yet** - Running from Python source code is adequately fast and resource efficient, even on very low-spec machines (4GB RAM)

### 📋 To Do
- **Language support** (English UI planned, contributions on other languages welcome)
- **Minor functional improvements** and performance enhancements

## 🛠️ Development

### ⚠️ Known Issue
`mlconjug3` requires `scikit-learn 1.3.0`, which in turn requires `numpy 1.25`, which is incompatible with Python 3.12.

**The Problem**:
- ✅ `scikit-learn 1.3.0` works just fine with `numpy 1.26.0` in reality
- ❌ The inaccurate dependency requirements of `scikit-learn 1.3.0` ruin Pip/Poetry's effort to resolve dependencies
- 🔧 A fix requires significant effort from package maintainers and is not happening anytime soon

**The Workaround**:
We have to duct tape our way out with `numpy (==1.26.0)`, overriding the internal dependency of `scikit-learn 1.3.0`.

## 🚀 Installation

### Prerequisites
- Python 3.8+
- PySide6
- Dependencies listed in `pyproject.toml`

### Install from Source
```bash
# Clone the repository
git clone <repository-url>
cd coucou

# Install dependencies with Poetry (recommended)
poetry install

# Or with pip
pip install -r requirements.txt

# Run the application
python main.py
```

## 📚 Usage

The interface of Coucou is designed to be self-intuitive.

If you envy more guidance :

Video tutorial in French: 
Manual in French (Work in progress): [Mode Emploi pour Coucou](CoucouManual-FR.py)

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

### Translations
- User interface in English and other languages
- Multilingual documentation

### Development
1. Fork the project
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Reporting Bugs
Use [GitHub Issues](../../issues) to report bugs or request features.

## 📄 License

This project is licensed under the free and open source AGPL3 license. See the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Qt/PySide community for the excellent framework
- Google TTS for text-to-speech services
- All contributors and users

## 📞 Contact

For any questions or suggestions, feel free to open an issue.

---

<div align="center">
  <sub>Made with ❤️ for the language learning community</sub>
</div>
