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
- **📝 PR Creation**: Create draft PRs on Azure DevOps or GitHub
- **🔐 Zero Config Auth**: Uses system credentials (`az login`, `gh auth login`)

## 🔐 Authentication

**Zero-Config Authentication** - Same pattern as professional tools like coding-flow!

This tool uses native SDKs with system credentials:

### Azure DevOps
Uses `ChainedTokenCredential` with automatic fallback:
1. **AzureCliCredential** - Uses token from `az login`
2. **InteractiveBrowserCredential** - Falls back to browser login if needed

```bash
# One-time setup
az login
```

### GitHub
Token resolution order:
1. `GITHUB_PAT_TOKEN` environment variable
2. `GITHUB_TOKEN` environment variable  
3. `gh auth token` command output

```bash
# One-time setup
gh auth login
```

### Required Python Packages
```bash
# For Azure DevOps
pip install azure-devops azure-identity msrest

# For GitHub
pip install PyGithub
```

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

The `config.env` file is optional - mainly for setting defaults:

```env
# Git configuration
DEFAULT_REMOTE=origin
DEFAULT_BASE_BRANCH=main

# Split configuration
DEFAULT_PR_COUNT=8
SPLIT_STRATEGY=by_module  # by_module, by_file, by_type, balanced
```

### Usage with VS Code + Copilot

Add to your VS Code `mcp.json`:

```json
{
  "servers": {
    "pr-splitter": {
      "command": "python",
      "args": ["/path/to/PR-Splitter-MCP/server.py"],
      "cwd": "/path/to/PR-Splitter-MCP",
      "type": "stdio"
    }
  }
}
```

## 🛠️ MCP Tools

### `check_auth_status`
Check authentication and dependency status for PR creation.

```
Output:
  - azure_devops: { authenticated, method, message }
  - github: { authenticated, method, message }
  - dependencies: { installed, missing, install_command }
  - ready: { ado: bool, github: bool }
```

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
  - source_path: Path to source files
  - target_repo_path: Target repository path
  - dry_run: Preview without making changes (default: True)
  
Output:
  - branches: List of created branches with commit hashes
  - summary: Success/failure statistics
  - status: Execution status
```

### `create_ado_pr`
Create a Pull Request in Azure DevOps.

```
Input:
  - org_url: Azure DevOps org URL (e.g., https://dev.azure.com/your-org)
  - project: Project name (e.g., MyProject)
  - repo: Repository name (e.g., my-repo)
  - source_branch: Source branch name
  - target_branch: Target branch name
  - title: PR title
  - description: PR description (optional)
  - draft: Create as draft (default: True)
  - work_item_id: ADO work item to link (optional)
  
Output:
  - pr_id: Created PR ID
  - pr_url: PR URL
  - status: Creation status
```

### `create_github_pr`
Create a Pull Request in GitHub.

```
Input:
  - repo: Repository in format "owner/repo"
  - source_branch: Source branch name
  - target_branch: Target branch name (default: main)
  - title: PR title
  - body: PR description (optional)
  - draft: Create as draft (default: True)
  
Output:
  - pr_id: Created PR ID
  - pr_url: PR URL
  - status: Creation status
```

### `create_prs_from_plan`
Batch create PRs from a split plan.

```
Input:
  - plan: Split plan from generate_split_plan
  - platform: "ado" or "github"
  - repo: Repository name
  - org_url: ADO org URL (required for ADO)
  - project: ADO project name (required for ADO)
  - draft: Create as draft PRs (default: True)
  
Output:
  - prs_created: Number of PRs created
  - pr_urls: List of PR URLs
  - results: Detailed results per PR
```

## 📋 Example Workflow

```
User: Split my code into 8 PRs
      Source: /path/to/my-feature
      Target: user/myname/feature-x

AI + MCP Server:
1. check_auth_status → Verify SDK authentication
2. analyze_code_structure → Understand the code
3. generate_split_plan → Create optimal split
4. [User confirms plan]
5. execute_split → Create branches and push
6. create_prs_from_plan → Create all PRs at once
```

## 🔄 Authentication Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    PR-Splitter-MCP                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Azure DevOps                    GitHub                     │
│  ┌─────────────────────┐        ┌─────────────────────┐    │
│  │ ChainedTokenCred    │        │ Token Resolution    │    │
│  │  ├─ AzureCliCred ◄──┼── az   │  ├─ GITHUB_PAT_TOKEN│    │
│  │  │   (from az login)│  login │  ├─ GITHUB_TOKEN    │    │
│  │  └─ BrowserCred     │        │  └─ gh auth token ◄─┼─gh │
│  │     (fallback)      │        │                     │auth│
│  └─────────────────────┘        └─────────────────────┘    │
│           │                              │                  │
│           ▼                              ▼                  │
│  ┌─────────────────────┐        ┌─────────────────────┐    │
│  │ azure-devops SDK    │        │ PyGithub SDK        │    │
│  │ (native API calls)  │        │ (native API calls)  │    │
│  └─────────────────────┘        └─────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
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
│   └── pr_creator.py      # PR creation (ADO/GitHub)
├── config.env             # Configuration (optional)
├── pyproject.toml         # Dependencies
└── README.md
```

## 🔧 CLI Commands Reference

### Azure DevOps CLI
```bash
# Login
az login

# Install DevOps extension
az extension add --name azure-devops

# Create PR manually
az repos pr create \
  --org https://dev.azure.com/your-org \
  --project MyProject \
  --repository my-repo \
  --source-branch user/yourname/feature \
  --target-branch main \
  --title "My PR" \
  --draft
```

### GitHub CLI
```bash
# Login
gh auth login

# Create PR manually
gh pr create \
  --repo owner/repo \
  --head feature-branch \
  --base main \
  --title "My PR" \
  --draft
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- Inspired by the need for better PR management in large teams
- Built with [FastMCP](https://github.com/jlowin/fastmcp)
- Thanks to the MCP community
