# PR-Splitter-MCP 🔀

A powerful Model Context Protocol (MCP) server that intelligently splits large Pull Requests into multiple smaller PRs for better code review and KPI tracking.

## 🎯 Problem Statement

Many companies have PR count requirements as KPIs, and large features often need to be split into multiple smaller PRs for:
- Better code review quality
- Easier tracking and management
- Meeting PR count targets
- Incremental feature delivery

**PR-Splitter-MCP** automates this process by analyzing code structure and intelligently splitting changes.

## ✨ Features

- **🔍 Code Analysis**: Analyze code structure, detect modules, and understand dependencies
- **🧠 Smart Splitting**: AI-powered splitting strategies based on:
  - Module boundaries
  - File types
  - Logical groupings
  - Dependency order
- **🌿 Branch Management**: Automatically create feature branches and sub-branches
- **📤 Auto Push**: Push all branches to remote repository
- **📝 PR Creation**: Optionally create draft PRs for each split

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/Polly2014/PR-Splitter-MCP.git
cd PR-Splitter-MCP

# Install with Poetry
poetry install

# Or with pip
pip install -e .
```

### Configuration

Create a `config.env` file:

```env
# Git configuration
DEFAULT_REMOTE=origin
DEFAULT_BASE_BRANCH=main

# Split configuration
DEFAULT_PR_COUNT=8
SPLIT_STRATEGY=by_module  # by_module, by_file, by_type

# ADO configuration (optional)
AZURE_DEVOPS_ORG_URL=https://dev.azure.com/your-org
AZURE_DEVOPS_PROJECT=YourProject
```

### Usage with VS Code + Copilot

Add to your VS Code `settings.json`:

```json
{
  "mcp": {
    "servers": {
      "pr-splitter": {
        "command": "poetry",
        "args": ["run", "pr-splitter-mcp"],
        "cwd": "/path/to/PR-Splitter-MCP"
      }
    }
  }
}
```

## 🛠️ MCP Tools

### `analyze_code_structure`
Analyze the code structure of a directory or PR.

```
Input:
  - source_path: Path to source directory
  - include_patterns: File patterns to include (e.g., "*.py")
  
Output:
  - modules: List of detected modules
  - files: File inventory with metadata
  - dependencies: Dependency graph between files
```

### `generate_split_plan`
Generate an intelligent split plan for the code.

```
Input:
  - source_path: Path to source directory
  - target_pr_count: Target number of PRs (default: 8)
  - strategy: Split strategy (by_module, by_file, by_type)
  - base_branch: Base branch name
  
Output:
  - plan: List of PR definitions with files and order
  - estimated_sizes: Size estimates per PR
  - dependency_order: Recommended merge order
```

### `execute_split`
Execute the split plan by creating branches and commits.

```
Input:
  - plan: Split plan from generate_split_plan
  - target_repo: Target repository path
  - branch_prefix: Prefix for branch names (e.g., "user/name/feature")
  - dry_run: Preview without making changes
  
Output:
  - branches: List of created branches
  - commits: Commit details per branch
  - status: Execution status
```

### `create_draft_prs`
Create draft PRs for all split branches (ADO/GitHub).

```
Input:
  - branches: List of branch names
  - target_branch: Target branch for PRs
  - pr_template: Optional PR description template
  
Output:
  - prs: List of created PR URLs
  - status: Creation status
```

## 📋 Example Workflow

```
User: Split my code into 8 PRs
      Source: /path/to/my-feature
      Target: user/myname/feature-x

AI + MCP Server:
1. analyze_code_structure → Understand the code
2. generate_split_plan → Create optimal split
3. [User confirms plan]
4. execute_split → Create branches and push
5. create_draft_prs → Create PRs in ADO
```

## 🏗️ Project Structure

```
PR-Splitter-MCP/
├── server.py              # Main MCP server
├── src/
│   ├── __init__.py
│   ├── analyzer.py        # Code structure analyzer
│   ├── splitter.py        # Split plan generator
│   ├── git_manager.py     # Git operations
│   └── pr_manager.py      # PR creation (ADO/GitHub)
├── config.env             # Configuration
├── pyproject.toml         # Dependencies
└── README.md
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- Inspired by the need for better PR management in large teams
- Built with [FastMCP](https://github.com/jlowin/fastmcp)
- Thanks to the MCP community
