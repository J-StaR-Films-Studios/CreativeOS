<div align="center">

```
   ██████╗██████╗ ███████╗ █████╗ ████████╗██╗██╗   ██╗███████╗ ██████╗ ███████╗
  ██╔════╝██╔══██╗██╔════╝██╔══██╗╚══██╔══╝██║██║   ██║██╔════╝██╔═══██╗██╔════╝
  ██║     ██████╔╝█████╗  ███████║   ██║   ██║██║   ██║█████╗  ██║   ██║███████╗
  ██║     ██╔══██╗██╔══╝  ██╔══██║   ██║   ██║╚██╗ ██╔╝██╔══╝  ██║   ██║╚════██║
  ╚██████╗██║  ██║███████╗██║  ██║   ██║   ██║ ╚████╔╝ ███████╗╚██████╔╝███████║
   ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═══╝  ╚══════╝ ╚═════╝ ╚══════╝
```

**Your Creative Nervous System — One CLI to Rule Your Entire Workflow**

[![Version](https://img.shields.io/badge/version-2.1.0-purple.svg)](https://github.com/JStaRFilms/CreativeOSFolder)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

[Installation](#-installation) • [Quick Start](#-quick-start) • [Commands](#-command-hub) • [Architecture](#-architecture) • [Docs](#-documentation)

</div>

---

## What is CreativeOS?

CreativeOS is a **context-aware CLI** that turns your file system into an intelligent, opinionated project management system. It bridges your active projects, Obsidian vault, archives, and portable drives through a single `cos` command.

Whether you're editing a YouTube video, writing code, producing a podcast, or designing for a client — CreativeOS gives every project the same structured foundation and keeps everything in sync.

**Why creators love it:**

- 🎯 **Instant Scaffolding** — 12+ templates for Video, Code, AI, Audio, Design, Photo, Writing, Podcast, Course, and Client work
- 🔄 **Obsidian Sync** — Bidirectional sync between project notes and your vault
- 🧠 **Context Awareness** — Run commands from *anywhere* inside a project (3-Level Up Rule)
- 📦 **Archive & Resurrect** — Move projects to cold storage. Bring them back when inspiration strikes
- 🚀 **Shuttle Drive** — Pack a project onto an external drive and keep working anywhere
- 🔒 **Security Hardened** — Input sanitization, path validation, and injection prevention baked in
- ⚡ **Beautiful CLI** — Rich terminal output with panels, tables, and progress indicators

---

## 📦 Installation

### Prerequisites

- **Python 3.10+** — [Download Python](https://www.python.org/downloads/)
- **pip** — Comes with Python

### Quick Install (Windows)

```bash
git clone https://github.com/JStaRFilms/CreativeOSFolder.git
cd CreativeOSFolder
python install_cos.py
```

The installer creates an isolated `.cos-venv`, installs the CLI from this checkout, and offers to run setup. It asks before adding `00_System/Bin` to your user PATH. Open a new PowerShell, cmd, or Git Bash terminal after accepting the PATH change, then run `cos --help` and `cos config validate`. If you decline, run `00_System/Bin/cos.bat` from PowerShell or cmd, or `00_System/Bin/cos` from Git Bash. The repository contains example configuration files, so the installer offers setup even if configuration files already exist; it backs them up before opening the wizard. When re-running setup, the wizard pre-fills current paths and categories and keeps settings it does not ask about. It does not overwrite configuration unless you confirm setup in the wizard.

### Manual Configuration

Copy the configuration template and customize paths:

```bash
cp 00_System/Config/config.template.json 00_System/Config/config.json
```

Edit `config.json` with your paths:

```json
{
  "root_path": "C:\\CreativeOS",
  "projects_path": "C:\\CreativeOS\\01_Projects",
  "vault_path": "C:\\CreativeOS\\03_Vault",
  "archive_path": "D:\\OneDrive - MSFT\\Archive",
  "shuttle_path": "A:\\CreativeOS_Shuttle"
}
```

### Windows Integration

`install_cos.py` can add `00_System/Bin` to your user PATH with permission. That directory contains a `cos` launcher for Git Bash and `cos.bat` for PowerShell and cmd. The older `00_System/Scripts/cos.bat` still works. Installing in another Python environment with `python -m pip install -e .` also provides a `cos` command when that environment is on PATH.

---

## 🚀 Quick Start

### Create Your First Project

```bash
# Create a video project
cos new "My YouTube Video" -c Video

# Create a code project with Git
cos new "My App" -c Code -g

# Create a client project
cos new "Brand Refresh" -c Design --client "Acme Corp"
```

### Adopt an Existing Folder

```bash
cd path/to/existing/project
cos init
```

### Sync Notes with Obsidian

```bash
cos sync
```

---

## 📋 Command Hub

### Creation

| Command | Description | Example |
|---------|-------------|---------|
| `new <name>` | Create a new project from template | `cos new "Video Project" -c Video` |
| `clone <url>` | Clone a Git repo and adopt it into COS | `cos clone https://github.com/user/repo.git` |
| `init` | Adopt current folder as a COS project | `cos init` |

### Maintenance

| Command | Description | Example |
|---------|-------------|---------|
| `sync` | Sync project notes with Obsidian vault | `cos sync` |
| `thumbs` | Generate global thumbnail gallery | `cos thumbs` |
| `clean` | Sort and categorise Downloads folder | `cos clean` |
| `sort-exports` | File Exports/_Inbox into Year/Month | `cos sort-exports` |
| `storage review` | Review cached project size, activity, media, and regenerable code space | `cos storage review` |

### Workflow

| Command | Description | Example |
|---------|-------------|---------|
| `export` | Open the project or month export folder | `cos export` |
| `travel` | Copy active project to shuttle drive | `cos travel` |
| `resurrect` | Restore an archived project to active | `cos resurrect "Old Project"` |

### Management & Studio
| Command | Description | Example |
|---------|-------------|---------|
| `gui` | Launch visual Web Studio in browser | `cos gui` |
| `gui --install-shortcut` | Build `CreativeOS.exe` and create Desktop/Taskbar shortcut | `cos gui --install-shortcut` |
| `app` | Launch standalone self-contained desktop app | `cos app` |
| `setup` | Configure CreativeOS (paths, categories, reset) | `cos setup` |
| `config` | View and edit configuration | `cos config show` |
| `category` | Manage project categories | `cos category list` |

### Help

| Command | Description | Example |
|---------|-------------|---------|
| `help` | Show help for commands | `cos help new` |
| `--help` | Command-specific help | `cos new --help` |

> **Tip:** Just type `cos` with no arguments to see the full Rich-formatted command hub in your terminal.

---

## 🎨 Categories & Templates

CreativeOS ships with 12+ project categories, each with an optimized folder structure:

| Category | Icon | Template | Description |
|----------|------|----------|-------------|
| Video | 🎬 | `video_project` | YouTube, film, video production |
| Code | 💻 | `plain_code` | Software development |
| Audio | 🎵 | `audio_project` | Music and audio production |
| AI | 🤖 | `ai_project` | Machine learning and AI projects |
| Design | 🎨 | `design_project` | Graphic design and branding |
| Photo | 📷 | `photo_project` | Photography projects |
| Writing | ✍️ | `writing_project` | Articles, blogs, books |
| Podcast | 🎙️ | `podcast_project` | Podcast production |
| Course | 📚 | `course_project` | Online course creation |
| Client | 👥 | `client_project` | Multi-discipline client work |

### Category Aliases

```bash
# These are equivalent
cos new "Project" -c Web    # → Code category
cos new "Project" -c ML     # → AI category
cos new "Project" -c Blog   # → Writing category
```

---

## 🧠 Architecture

### Hub-and-Spoke Design

```
┌─────────────────────────────────────────────────────────────────┐
│                         CreativeOS                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐   │
│  │ Projects │◄──►│  Vault   │◄──►│ Archive  │◄──►│ Shuttle  │   │
│  │  (Hub)   │    │ (Notes)  │    │ (Cold)   │    │ (Mobile) │   │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘   │
│       │                                                         │
│       ▼                                                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Templates                             │   │
│  │  Video │ Audio │ Design │ Photo │ Code │ Writing         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

- **Projects Path** — Active workspace for current projects
- **Vault Path** — Obsidian vault for notes and knowledge base
- **Archive Path** — Cold storage for completed projects
- **Shuttle Path** — External drive for portable work

### Project DNA (`.project_meta.json`)

Every project carries a metadata file that defines its identity:

```json
{
  "name": "My Video Project",
  "type": "Video",
  "created": "2026-02-25",
  "client": "Client Name",
  "git": "https://github.com/user/repo.git",
  "tags": ["youtube", "tutorial"],
  "status": "active"
}
```

### The 3-Level Up Rule

Run commands from anywhere inside a project — CreativeOS walks up to find your project root:

```
C:\CreativeOS\01_Projects\Video\2026_Nike_Ad\04_Exports\Social_Media\Revisions\
         │
         │  cos export
         ▼
    Searches upward for .project_meta.json
    Found at: C:\CreativeOS\01_Projects\Video\2026_Nike_Ad\
```

---

## 🔧 Command Reference

### `cos gui` & `cos app` — Visual Studio Hub & Desktop App

CreativeOS includes a visual Web GUI and a native self-contained desktop launcher.

```bash
# 1. Launch in your default browser (foreground terminal server)
cos gui

# 2. Launch in standalone desktop app mode
cos app
# or
cos gui --app

# 3. Create Windows Desktop / Start Menu shortcut (pin-ready to Taskbar)
cos gui --install-shortcut
```

#### Self-Contained Desktop App (`CreativeOS.exe`)
When you run `cos gui --install-shortcut`:
1. It automatically compiles a native Windows executable (`CreativeOS.exe`) using the built-in Windows C# compiler (`csc.exe`).
2. Creates `CreativeOS.lnk` on your Desktop and Start Menu with the official icon embedded.
3. You can right-click the Desktop shortcut and click **"Pin to taskbar"**.
4. Clicking the taskbar icon automatically starts the background server, launches the standalone frameless Edge/Chrome app window, and cleanly shuts down the server when the window is closed.

---

### `cos storage` — Project Storage Review

CreativeOS can maintain a **read-only** local storage index at
`00_System/Config/storage_index.json`. It reports each initialized project's
created date, last meaningful update (ignoring generated folders such as
`node_modules`, `.git`, and build caches), total size, media size, and space in
regenerable folders. It never moves or deletes anything.

```bash
# Instant: show the last background scan
cos storage

# Get the same examples and flags shown in the terminal
cos help storage
cos storage review --help

# Deliberately scan now and update the local index
cos storage review --refresh

# Sort the review by code/cache savings or media usage
cos storage review --sort reclaimable
cos storage review --sort media

# Schedule a low-priority Sunday scan and opt into occasional cache-only reminders
cos storage schedule --time 03:00

# Inspect or remove the Windows Task Scheduler entry
cos storage schedule --status
cos storage schedule --remove
```

The scheduled task runs `cos storage scan --quiet --background`; it measures
files at low priority and can never archive or delete project data. Normal
CreativeOS commands only read the small cached JSON file, so they never trigger
a disk scan.

### `cos new` — Create Project

```bash
cos new <name> [options]

Arguments:
  name                    Project name (required)

Options:
  -c, --category CATEGORY Category: Video, Code, AI, Audio, Design, Photo, Writing, Podcast, Course, Client
                          Default: Video
  --client CLIENT         Associate with a client (creates client subfolder)
  -d, --date DATE         Backdate project (YYYY-MM-DD)
  -g, --git               Initialize Git repository
  -s, --simple            Use minimal folder structure

Examples:
  cos new "YouTube Tutorial" -c Video -g
  cos new "Mobile App" -c Code --client "Acme Corp" -g
  cos new "Podcast Episode 5" -c Podcast -d 2026-01-15
```

### `cos clone` — Clone Repository

```bash
cos clone <url> [options]

Arguments:
  url                     Git repository URL (required)

Options:
  -n, --name NAME         Override folder name
  -c, --category CATEGORY Category (default: Code)
  --client CLIENT         Associate with a client

Examples:
  cos clone https://github.com/user/repo.git
  cos clone https://github.com/user/repo.git -n "My Project" -c AI
```

### `cos sync` — Bidirectional Sync

```bash
cos sync --dry-run   # Preview copies and updates without changing project/vault files or sync state
cos sync             # Apply the changes

Synchronizes 00_Notes folders between projects and Obsidian vault:
  • New in Project → Push to Vault
  • New in Vault → Pull to Project
  • Conflict → Newer file wins (with backup)
```

### `cos travel` — Archive Project

```bash
cos travel

Moves project to shuttle drive for portable work.
Creates _TRAVEL_LOG.txt with sync timestamp.
```

### `cos resurrect` — Restore Project

```bash
cos resurrect <name>

Searches archive for project and restores to active projects.
Reads .project_meta.json to determine original location.
```

---

## 🛡️ Security

CreativeOS v2.1.0 includes comprehensive security hardening:

- **Input Sanitization** — All user inputs are sanitized for safe path construction
- **Git URL Validation** — Prevents flag injection in clone operations
- **PowerShell Sanitization** — Escapes special characters in shell commands
- **Path Boundary Checks** — Validates paths stay within trusted directories
- **Secure File Permissions** — Restricts access to configuration files

See [SECURITY.md](SECURITY.md) for the full security policy.

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [USER MANUAL.md](USER%20MANUAL.md) | Comprehensive command reference & advanced topics |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture and design decisions |
| [CHANGELOG.md](CHANGELOG.md) | Version history and changes |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [SECURITY.md](SECURITY.md) | Security policy |

---

## 🧪 Development

### Setup Development Environment

```bash
# Clone and install dev dependencies
git clone https://github.com/JStaRFilms/CreativeOSFolder.git
cd CreativeOSFolder
pip install -e ".[dev]"
```

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=cos

# Type checking
mypy 00_System/Scripts/cos

# Linting
ruff check 00_System/Scripts/cos
```

### Project Structure

```
CreativeOS/
├── 00_System/
│   ├── Config/
│   │   ├── config.json          # User configuration
│   │   ├── config.template.json # Configuration template
│   │   └── categories.json      # Category definitions
│   ├── Scripts/
│   │   ├── cos/                 # Main package
│   │   │   ├── cli.py           # CLI entry point
│   │   │   ├── config.py        # Configuration management
│   │   │   ├── security.py      # Input validation
│   │   │   ├── file_utils.py    # File operations
│   │   │   └── commands/        # Command implementations
│   │   └── tests/               # Test suite
│   └── Templates/               # Project templates
├── pyproject.toml               # Package metadata
├── requirements.txt             # Dependencies
└── README.md                    # You are here
```

---

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Built with [Rich](https://github.com/Textualize/rich) for beautiful terminal output
- Inspired by the need for a unified creative workflow system

---

<div align="center">

**[⬆ Back to Top](#)**

Built with 🔥 by [Oluleke-Oke Goodness CEO J Star Films Studios](https://github.com/JStaRFilms)

</div>
