# CreativeOS — User Manual

> **Your Creative Nervous System** · v2.1.0

CreativeOS is a context-aware CLI that transforms your file system into an intelligent project management system. It bridges your active projects, Obsidian vault, archives, and portable drives through a unified `cos` command interface.

## Installation and Configuration

### Installation

CreativeOS requires **Python 3.10+** and is managed through the `cos` CLI. To get started:

1. Ensure you have [Python 3.10+](https://www.python.org/downloads/) installed on your system.

2. On Windows, run `python install_cos.py` from the CreativeOS checkout. It creates an isolated Python environment, installs the CLI, and offers setup. It asks before adding `00_System/Bin` to your user PATH. Restart your terminal after accepting, then use `cos` in PowerShell, cmd, or Git Bash.

3. If you skip the PATH change, run the launcher directly from `00_System/Bin`: `cos.bat` in PowerShell or cmd, or `cos` in Git Bash. You can also install into an existing Python environment with `python -m pip install -e .` and put that environment's command directory on PATH.

### Configuration

CreativeOS reads `00_System/Config/config.json` for its paths. The checkout includes a sample configuration, which may point to another user's directories. The Windows installer offers to run `cos setup` and saves backups of any existing configuration before opening the wizard. Re-running setup starts with your current paths and categories and keeps settings the wizard does not ask about, such as `downloads_path`. If you skip setup, inspect `cos config show` and run `cos config validate` before creating projects. The validation command exits with status 1 when it finds problems.

The key paths defined in the configuration file are:

- `root_path`: The base directory for the entire CreativeOS system. This is the root where all operations are anchored.

- `projects_path`: The directory where all projects are stored. New projects created through the system will be placed here.

- `exports_path`: The location for project exports. Exports are organized by year and month for easy archiving and retrieval.

- `templates_path`: The directory containing project templates. Available templates include `simple`, `code_project`, and `video_project`, which provide starting structures for different types of projects.

- `vault_path`: The path to an Obsidian vault used for syncing notes and documentation related to projects.

- `downloads_path`: The user's default Downloads folder. This is utilized by the `clean` command to manage downloaded files.

- `shuttle_path`: The path to an external drive. This is used by the `travel` command for transferring projects or data.

- `archive_path`: The location for archived projects. Projects moved here can be restored using the `resurrect` command.

Make sure all paths in the configuration file point to valid directories on your system. Incorrect paths may cause commands to fail.

## Core Concepts

### Project-Based Workflow
Everything in CreativeOS is organized into distinct projects. This approach ensures that each initiative, whether it's a video production, code development, or AI experiment, is contained within its own dedicated space, promoting clarity and isolation.

### Categorization
Projects are sorted into categories such as "Video", "Code", and "AI", which correspond to physical folders on the filesystem. This categorization allows for easy navigation and management. Additionally, projects can be grouped under a client folder, enabling hierarchical organization for client-specific work.

### Project Metadata
Each project contains a critical file called `.project_meta.json` in its root directory. This file stores essential information including the project name, category, creation date, and other relevant metadata. The system intelligently searches for this file to understand the project's context and apply appropriate behaviors.

### Templates
CreativeOS utilizes project templates located in the `templates_path` directory. The `new` command leverages these templates, which are defined by `structure.json` files, to create consistent folder structures for different types of projects. Examples include `code_project`, `video_project`, and `simple`, ensuring that new projects start with a standardized and efficient layout.

### Notes and Vault Syncing
Within each project, a `00_Notes` directory is dedicated to storing markdown-based notes. The `sync` command performs a bidirectional synchronization between these project-specific notes and a central location defined by the `vault_path`. This feature is particularly useful for integration with tools like Obsidian, allowing seamless note management across projects.

## Commands

### 1. `new <name>`
**Description**: Spawns a new project with the specified name, creating a structured directory based on the chosen template and category.

**Arguments**:
- `name` (required): The name of the new project.
- `-c/--category` (optional, default: "Video"): Specifies the category for the project (e.g., "Video", "Code", "AI"). The project will be placed in the corresponding subdirectory under `projects_path`.
- `-s/--simple` (optional): Uses a simplified project structure instead of the full template.
- `-d/--date` (optional): Includes the current date in the project name or metadata.
- `--client` (optional): Associates the project with a client, creating it under a client-specific folder.
- `-g/--git` (optional): Initializes a Git repository in the new project directory.

**Detailed Explanation**: This command creates a new project directory in the `projects_path` under the specified category. It copies the appropriate template structure from `templates_path` (e.g., `video_project` for Video category) to ensure consistency. If `-s/--simple` is used, it applies a minimal structure. The `.project_meta.json` file is generated with metadata including name, category, creation date, and client if specified. If `-g/--git` is provided, it runs `git init` in the project root. The command validates that the name is unique within the category and ensures all paths exist.

**Example**:
```
cos new MyVideoProject -c Video --client AcmeCorp -g
```
This creates a new video project named "MyVideoProject" under the "Video/AcmeCorp" directory, initializes Git, and uses the full video template.

### 2. `clone <url>`
**Description**: Clones a Git repository from the provided URL and adopts it as a CreativeOS project.

**Arguments**:
- `url` (required): The Git repository URL to clone.
- `-n/--name` (optional): Specifies a custom name for the cloned project; if not provided, uses the repository name.
- `-c/--category` (optional, default: "Code"): Sets the category for the project (e.g., "Code").
- `-d/--date` (optional): Includes the current date in the project metadata.
- `--client` (optional): Associates the project with a client.

**Detailed Explanation**: This command performs a `git clone` of the specified URL into the `projects_path` under the chosen category. It then generates a `.project_meta.json` file to integrate the cloned repository into the CreativeOS system. If a custom name is provided, it renames the cloned directory accordingly. The category defaults to "Code" for cloned repos. Client association creates a subfolder. The command ensures the clone succeeds and updates metadata with clone date and source URL.

**Example**:
```
cos clone https://github.com/user/repo.git -n MyClonedProject -c Code --client ClientX
```
This clones the repository into "Code/ClientX/MyClonedProject" and sets up the project metadata.

### 3. `init`
**Description**: Initializes the current directory as a CreativeOS project by generating the necessary metadata file.

**Arguments**: None.

**Detailed Explanation**: This command scans the current working directory for existing files and creates a `.project_meta.json` file with inferred metadata. It determines the project name from the directory name, category from the path or defaults, and sets the creation date to the current time. If the directory is already a project (has `.project_meta.json`), it updates the metadata instead. This allows adopting existing folders into the CreativeOS workflow without recreating them.

**Example**:
```
cos init
```
Run this in an existing project directory to initialize it as a CreativeOS project.

### 4. `export`
**Description**: Opens the export folder in the file explorer for easy access to exported projects.

**Arguments**:
- `-s/--simple` (optional): Opens a simplified view or specific subfolder of the exports.

**Detailed Explanation**: This command launches the file explorer (e.g., Windows Explorer) to the `exports_path` directory. Exports are organized by year and month subfolders. If `-s/--simple` is used, it may open a specific simplified export location or filter the view. This facilitates quick access to exported files without navigating manually.

**Example**:
```
cos export
```
Opens the main exports folder.

### 5. `sync`
**Description**: Synchronizes project notes with the central Obsidian vault for unified documentation management.

**Arguments**: None.

**Detailed Explanation**: This command performs bidirectional synchronization between the `00_Notes` directory in each project and the `vault_path`. It copies new or updated markdown files from projects to the vault and vice versa, ensuring notes are consistent across locations. The sync handles conflicts by preferring the most recently modified version and logs any issues. This is essential for maintaining centralized knowledge bases integrated with Obsidian.

**Example**:
```
cos sync
```
Synchronizes all project notes with the vault.

### 6. `thumbs`
**Description**: Updates the thumbnail gallery by regenerating or refreshing project thumbnails.

**Arguments**: None.

**Detailed Explanation**: This command scans projects for image files (e.g., thumbnails or previews) and updates a centralized gallery. It may resize images, generate new thumbnails from project assets, and organize them in a viewable format. This is useful for visual project overviews, especially in creative workflows like video or design projects.

**Example**:
```
cos thumbs
```
Regenerates thumbnails for all projects.

### 7. `clean [target]`
**Description**: Sorts and organizes the Downloads folder by moving files into categorized subfolders.

**Arguments**:
- `target` (optional): Specifies a particular file or folder within Downloads to clean; if omitted, cleans the entire Downloads folder.

**Detailed Explanation**: This command analyzes the `downloads_path` (user's Downloads folder) and moves files into organized subdirectories based on file type (e.g., Images, Documents, Videos). If a target is specified, it focuses on that item. It handles duplicates by renaming and ensures no files are overwritten without confirmation. This maintains a tidy Downloads folder aligned with CreativeOS organization principles.

**Example**:
```
cos clean
```
Sorts the entire Downloads folder.

### 8. `sort-exports`
**Description**: Sorts the export inbox by organizing exported files into proper dated folders.

**Arguments**: None.

**Detailed Explanation**: This command processes the export inbox (likely a staging area in `exports_path`) and moves files into year/month subfolders based on their creation or modification dates. It ensures exports are archived systematically, preventing clutter and aiding long-term retrieval. The command may also validate file integrity during sorting.

**Example**:
```
cos sort-exports
```
Organizes the export inbox.

### 9. `travel`
**Description**: Copies the current or specified project to the shuttle drive for portable access.

**Arguments**: None.

**Detailed Explanation**: This command identifies the current project (based on working directory or metadata) and copies it to the `shuttle_path` (external drive). It preserves the project structure and metadata, allowing work on the go. If the project already exists on the shuttle, it updates it incrementally. This is ideal for transferring projects between systems or working offline.

**Example**:
```
cos travel
```
Copies the current project to the shuttle drive.

### 10. `resurrect <name>`
**Description**: Restores a previously archived project back to the active projects directory.

**Arguments**:
- `name` (required): The name of the archived project to restore.

**Detailed Explanation**: This command searches the `archive_path` for the specified project name, copies it back to the appropriate category under `projects_path`, and updates its metadata to reflect restoration. It ensures the project is fully functional upon resurrection, including reintegrating with notes sync if applicable. If the project name conflicts with an active one, it prompts for resolution.

**Example**:
```
cos resurrect OldProject
```
Restores "OldProject" from the archive to active projects.

### 11. `gui`
**Description**: Launches the CreativeOS Web Studio dashboard in your browser or desktop app mode.

**Arguments / Options**:
- `-a`, `--app`: Launch in self-contained standalone desktop app mode.
- `--install-shortcut`: Automatically compile `CreativeOS.exe` and create Windows Desktop & Start Menu shortcuts.
- `-p`, `--port`: Custom port (default: 8787).
- `--no-browser`: Start the server without automatically opening the browser.

**Example**:
```bash
cos gui                     # Launch in default browser
cos gui --app               # Launch in standalone desktop mode
cos gui --install-shortcut  # Generate taskbar-ready executable & shortcuts
```

### 12. `app`
**Description**: Direct alias for `cos gui --app` to run the self-contained desktop app with automated server lifecycle management.

**Example**:
```bash
cos app
```

## Advanced Topics and Intelligent Behaviors
### Smart Date Detection
The script employs intelligent date inference when creating project metadata. If no explicit creation date is provided, it analyzes the median modification timestamps of all files within the project folder. This approach provides a reasonable approximation of when the project was actually started, based on the collective "age" of its contents, ensuring accurate chronological organization even for projects without explicit date tracking.

### Bidirectional Syncing
The `sync` command implements sophisticated bidirectional synchronization with intelligent conflict resolution. It compares file modification times between project notes and the central vault, always prioritizing the newer version. In the rare case of identical timestamps (a tie), the system creates a backup of the conflicting file before proceeding, preventing any data loss and allowing manual review if needed.

### Path-Based Inference
Commands like `init` and `new` automatically detect project context from the directory structure. When run in a subdirectory, the script infers the client or category based on the folder hierarchy. For example, executing `init` in `projects/Video/ClientX/MyProject/` will automatically set the category to "Video" and associate it with "ClientX" as the client, eliminating the need for manual specification and reducing user input.

### Automatic Template Selection
The `new` command intelligently selects the most appropriate project template based on the specified category. For instance, choosing the "AI" category automatically applies the `ai_project` template, which includes specialized folders for datasets, models, and notebooks. This ensures that each project starts with a structure optimized for its intended purpose, promoting consistency and efficiency across different project types.

### Robust File Operations
The script is designed to handle common file system challenges, particularly those encountered with cloud storage services like OneDrive. It includes retry mechanisms for operations on locked or temporarily inaccessible files, automatically attempting the operation multiple times with brief pauses. This resilience ensures reliable performance even in environments where files may be in use by other applications or syncing processes.

### Automated Git Integration
When using the `-g` flag with the `new` command, the script not only initializes a Git repository but also automatically applies a universal `.gitignore` file. This file is sourced from the templates directory and includes common exclusions for various file types, operating systems, and development environments, providing immediate best-practice version control setup without manual configuration.

### Conflict and Duplicate Handling
To prevent data loss during operations like `sort-exports`, the system implements a versioning strategy for conflicts. When encountering a file with a name that already exists in the target location, it creates a versioned duplicate (e.g., `file_v2.txt`) instead of overwriting. This approach preserves all data while allowing the operation to complete successfully, with the ability to manually resolve duplicates later.

### Client Grouping
CreativeOS supports hierarchical organization through client grouping, allowing multiple projects to be organized under a single client folder. This structure (e.g., `projects/Video/AcmeCorp/ProjectA`, `projects/Code/AcmeCorp/ProjectB`) enables better organization for client-specific work, making it easier to manage and navigate related projects while maintaining clear separation between different clients.