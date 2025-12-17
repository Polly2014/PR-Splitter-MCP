# PR-Splitter-MCP 🔀

[![PyPI version](https://badge.fury.io/py/pr-splitter-mcp.svg)](https://badge.fury.io/py/pr-splitter-mcp)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A powerful Model Context Protocol (MCP) server that intelligently splits large Pull Requests into multiple smaller PRs for better code review and KPI tracking.

**🤝 Designed to work seamlessly with [coding-flow MCP](https://github.com/user/coding-flow)!**

## 📦 Installation

### Via PyPI (Recommended)

```bash
pip install pr-splitter-mcp
```

### Via uvx (Quick Start)

```bash
uvx pr-splitter-mcp
```

### From Source

```bash
git clone https://github.com/Polly2014/PR-Splitter-MCP.git
cd PR-Splitter-MCP
poetry install
```

## ⚙️ MCP Configuration

Add to your VS Code MCP settings (`settings.json` or `mcp.json`):

```json
{
  "mcp": {
    "servers": {
      "pr-splitter": {
        "command": "uvx",
        "args": ["pr-splitter-mcp"]
      }
    }
  }
}
```

Or if installed via pip:

```json
{
  "mcp": {
    "servers": {
      "pr-splitter": {
        "command": "pr-splitter-mcp"
      }
    }
  }
}
```

## 🎯 Problem Statement

Many companies have PR count requirements as KPIs, and large features often need to be split into multiple smaller PRs for:
- Better code review quality
- Easier tracking and management
- Meeting PR count targets
- Incremental feature delivery

**PR-Splitter-MCP** automates this process by analyzing code structure and intelligently splitting changes.

## 🔄 Workflow with coding-flow MCP

The recommended workflow combines PR-Splitter-MCP with coding-flow for optimal results:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        PR Split Workflow                                 │
├─────────────────────────────────────────────────────────────────────────┤
│  1. coding-flow.get_pr_content(prId)     → Get PR files & changes       │
│                         ↓                                                │
│  2. pr-splitter.generate_split_plan_from_pr(files, count, strategy)     │
│                         ↓                                                │
│  3. Git operations (create branches, copy files, push)                  │
│                         ↓                                                │
│  4. coding-flow.create_draft_pr() × N    → Create sub-PRs               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Example Conversation

```
User: Split PR #6243094 into 5 smaller PRs

AI Agent:
1. Uses coding-flow.get_pr_content() to get 12 changed files
2. Uses pr-splitter.generate_split_plan_from_pr() to create split plan:
   - PR 1/5: configs (4 files)
   - PR 2/5: utils (3 files)
   - PR 3/5: components (2 files)
   - PR 4/5: models (2 files)
   - PR 5/5: inference (1 file)
3. Creates branches and commits for each split
4. Uses coding-flow.create_draft_pr() to create 5 draft PRs
```

## ✨ Features

- **🔍 Code Analysis**: Analyze code structure, detect modules, and understand dependencies
- **🧠 Smart Splitting**: AI-powered splitting strategies based on:
  - Module boundaries
  - File types
  - Logical groupings
  - Dependency order
- **🤝 coding-flow Integration**: `generate_split_plan_from_pr` works directly with PR data
- **📁 Folder Support**: `split_folder_to_plan` and `split_and_push_folder` for local code
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

### Core Tools (for coding-flow integration)

#### `generate_split_plan_from_pr` ⭐ NEW
Generate a split plan directly from PR file data (from coding-flow.get_pr_content).

**This is the recommended tool to use with coding-flow MCP!**

```
Input:
  - pr_files: List of files from coding-flow.get_pr_content()
  - target_pr_count: Target number of PRs (default: 5)
  - strategy: Split strategy (by_module, by_file, by_type, balanced)
  - base_branch: Base branch for split PRs
  - branch_prefix: Prefix for branch names
  - pr_title_prefix: Prefix for PR titles

Output:
  - plan: { prs: [...], base_branch, branch_prefix }
  - summary: { total_files, total_lines, files_per_pr, lines_per_pr }
  - merge_order: Recommended merge sequence
  - workflow_next_steps: Git commands to execute
```

#### `generate_pr_descriptions` ⭐ NEW
Generate detailed PR titles and descriptions for a split plan.

```
Input:
  - plan: Split plan from generate_split_plan_from_pr
  - project_name: Name for PR titles
  - include_dependencies: Include dependency info

Output:
  - prs: Enhanced PRs with professional titles and descriptions
  - ready_for_creation: Boolean indicating readiness
```

### Analysis Tools

#### `check_auth_status`
Check authentication and dependency status for PR creation.

```
Output:
  - azure_devops: { authenticated, method, message }
  - github: { authenticated, method, message }
  - dependencies: { installed, missing, install_command }
  - ready: { ado: bool, github: bool }
```

#### `analyze_code_structure`
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

#### `get_split_strategies`
Get available split strategies with descriptions and workflow guidance.

```
Output:
  - strategies: { by_module, by_file, by_type, balanced }
  - workflow: Recommended steps with coding-flow
```

### Folder-based Split Tools ⭐ NEW

#### `split_folder_to_plan`
Generate a split plan from a local folder (similar to generate_split_plan_from_pr).

```
Input:
  - folder_path: Path to folder containing code to split
  - target_pr_count: Target number of PRs (default: 5)
  - strategy: Split strategy (by_module, by_file, by_type, balanced)
  - base_branch: Base branch for split PRs
  - branch_prefix: Prefix for branch names
  - include_patterns: File patterns to include (e.g., ["*.py", "*.js"])
  - exclude_patterns: File patterns to exclude (e.g., ["__pycache__/*"])

Output:
  - plan: Split plan with PR definitions
  - summary: { total_files, total_lines, files_per_pr, lines_per_pr }
  - workflow_next_steps: Instructions for next steps
```

#### `split_and_push_folder` ⭐ End-to-End
All-in-one: Analyze folder, create branches, copy files, commit, and push.

```
Input:
  - source_folder: Path to folder containing code
  - target_repo_path: Path to target git repository
  - target_pr_count: Target number of PRs (default: 5)
  - strategy: Split strategy
  - base_branch: Base branch in target repo
  - branch_prefix: Prefix for branch names
  - relative_path_in_repo: Where to put files in repo (e.g., "src/feature/")
  - include_patterns: File patterns to include
  - exclude_patterns: File patterns to exclude
  - dry_run: Preview without changes (default: True)
  - push: Push branches to remote (default: True)

Output:
  - plan: The split plan used
  - branches: Created branches with status
  - next_steps: How to create the PRs
```

### Planning & Execution Tools

#### `generate_split_plan`
Generate an intelligent split plan for local code directory.

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

#### `execute_split`
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

### PR Creation Tools

#### `create_ado_pr`
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

#### `create_github_pr`
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

#### `create_prs_from_plan`
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

## 📋 Example Workflows

### Workflow 1: Split Existing PR (with coding-flow) ⭐ Recommended

```
User: Split PR #6243094 into 5 PRs targeting user/feature-test

AI Agent + MCP Servers:
1. coding-flow.get_pr_content(prIdOrUrl="PR#6243094")
   → Returns 12 changed files with paths and change types

2. pr-splitter.generate_split_plan_from_pr(
     pr_files=<files from step 1>,
     target_pr_count=5,
     strategy="by_module",
     base_branch="user/feature-test"
   )
   → Returns split plan with 5 PRs

3. Git operations:
   - git checkout -b user/feature-test (base branch)
   - For each PR in plan:
     - git checkout -b <branch_name> user/feature-test
     - git checkout <source_branch> -- <files>
     - git commit && git push

4. For each PR:
   coding-flow.create_draft_pr(
     branchName=<branch>,
     targetBranch="user/feature-test",
     title=<title>,
     description=<description>
   )
```

### Workflow 2: Split Local Folder (End-to-End) ⭐ NEW

```
User: Split /path/to/my-feature into 5 PRs and push to my-repo

AI Agent + MCP Server:
1. pr-splitter.split_and_push_folder(
     source_folder="/path/to/my-feature",
     target_repo_path="/path/to/my-repo",
     target_pr_count=5,
     strategy="by_module",
     base_branch="user/myname/feature",
     branch_prefix="user/myname/feature",
     relative_path_in_repo="src/feature/",
     dry_run=False,
     push=True
   )
   → Creates 5 branches, copies files, commits, and pushes

2. pr-splitter.create_prs_from_plan(
     plan=<plan from step 1>,
     platform="ado",
     org_url="https://dev.azure.com/myorg",
     project="MyProject",
     repo="my-repo"
   )
   → Creates 5 draft PRs

Done! 5 PRs created from local folder.
```

### Workflow 3: Split Local Code (Step by Step)

```
User: Split my code into 8 PRs
      Source: /path/to/my-feature
      Target: user/myname/feature-x

AI + MCP Server:
1. check_auth_status → Verify SDK authentication
2. split_folder_to_plan → Generate split plan with preview
3. [User confirms plan]
4. split_and_push_folder(dry_run=False) → Create branches and push
5. create_prs_from_plan → Create all PRs at once
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
