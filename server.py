"""
PR-Splitter-MCP Server
A FastMCP-based server for intelligently splitting large PRs into smaller ones.

Designed to work seamlessly with coding-flow MCP:
- coding-flow: get_pr_content, create_draft_pr (ADO operations)
- pr-splitter: analyze, plan, execute split (split logic)

Usage Flow:
1. coding-flow.get_pr_content() → Get PR files
2. pr-splitter.generate_split_plan_from_pr() → Generate split plan from PR data
3. Git operations (create branches, copy files)
4. coding-flow.create_draft_pr() → Create PRs
"""

import asyncio
import logging
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastmcp import FastMCP
from dotenv import load_dotenv

from src.analyzer import CodeAnalyzer
from src.splitter import SplitPlanner, SplitStrategy
from src.git_manager import GitManager
from src.pr_creator import PRCreator

# Load environment variables
load_dotenv('config.env')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pr_splitter.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class PRSplitterMCPServer:
    """
    PR-Splitter MCP Server
    Provides tools for analyzing code and splitting into multiple PRs.
    """
    
    def __init__(self):
        """Initialize the PR-Splitter MCP Server."""
        # Initialize FastMCP server
        self.mcp = FastMCP("PR-Splitter-MCP")
        
        # Initialize components
        self.analyzer = CodeAnalyzer()
        self.planner = SplitPlanner()
        self.git_manager = GitManager()
        self.pr_creator = PRCreator()
        
        # Server statistics
        self.stats = {
            "start_time": datetime.now(),
            "analyses_performed": 0,
            "plans_generated": 0,
            "splits_executed": 0,
            "prs_created": 0
        }
        
        # Register tools
        self._register_tools()
        
        logger.info("PR-Splitter MCP Server initialized")
    
    def _categorize_files(self, files: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
        """Categorize files by module/directory and type."""
        categorized = {
            "configs": [],
            "docs": [],
            "modules": {},  # module_name -> files
            "other": []
        }
        
        config_patterns = ['.yaml', '.yml', '.json', '.toml', '.ini', '.env', '.cfg']
        doc_patterns = ['.md', '.rst', '.txt', 'README', 'LICENSE', 'CHANGELOG']
        root_files = ['.gitignore', 'requirements.txt', 'setup.py', 'pyproject.toml']
        
        # First pass: find common prefix to strip
        paths = [f.get("path", "") for f in files]
        if paths:
            # Find common directory prefix
            common_parts = paths[0].split('/')
            for p in paths[1:]:
                parts = p.split('/')
                new_common = []
                for i, (a, b) in enumerate(zip(common_parts, parts)):
                    if a == b:
                        new_common.append(a)
                    else:
                        break
                common_parts = new_common
            common_prefix = '/'.join(common_parts)
            if common_prefix:
                common_prefix += '/'
        else:
            common_prefix = ''
        
        for f in files:
            path = f.get("path", "")
            basename = os.path.basename(path)
            
            # Strip common prefix to get relative path
            rel_path = path[len(common_prefix):] if path.startswith(common_prefix) else path
            
            # Check if root/config file (non-code files)
            if basename in root_files:
                categorized["other"].append(f)
            # Check if config file
            elif any(path.endswith(p) for p in config_patterns) or 'config' in path.lower():
                categorized["configs"].append(f)
            # Check if doc file
            elif any(p in basename for p in doc_patterns):
                categorized["docs"].append(f)
            # Check module based on RELATIVE path
            else:
                parts = rel_path.split('/')
                if len(parts) > 1:
                    # Use first directory in relative path as module
                    module = parts[0]
                    
                    if module not in categorized["modules"]:
                        categorized["modules"][module] = []
                    categorized["modules"][module].append(f)
                else:
                    # Root-level code files go to "core" module
                    if path.endswith('.py') or path.endswith('.js') or path.endswith('.ts'):
                        if "core" not in categorized["modules"]:
                            categorized["modules"]["core"] = []
                        categorized["modules"]["core"].append(f)
                    else:
                        categorized["other"].append(f)
        
        return categorized
    
    def _split_pr_by_module(self, categorized: Dict, target_count: int, 
                            branch_prefix: str, title_prefix: str) -> List[Dict]:
        """Split files by module/directory."""
        prs = []
        pr_index = 1
        
        # PR1: Configs and docs (setup)
        setup_files = categorized["configs"] + categorized["docs"] + categorized["other"]
        if setup_files:
            prs.append({
                "index": pr_index,
                "name": "configs",
                "branch_name": f"{branch_prefix}-configs",
                "title": f"{title_prefix}: Configuration and documentation",
                "files": [f["path"] for f in setup_files],
                "description": "Project setup: configs, docs, and root files",
                "depends_on": []
            })
            pr_index += 1
        
        # Remaining PRs: By module
        modules = list(categorized["modules"].items())
        
        # Calculate remaining slots for modules
        remaining_slots = target_count - pr_index + 1
        
        # If too many modules, combine some
        if len(modules) > remaining_slots:
            # Sort by file count, combine smallest
            modules.sort(key=lambda x: len(x[1]))
            while len(modules) > remaining_slots:
                small1 = modules.pop(0)
                small2 = modules.pop(0) if modules else (None, [])
                combined_name = f"{small1[0]}_{small2[0]}" if small2[0] else small1[0]
                combined_files = small1[1] + (small2[1] if small2[1] else [])
                modules.append((combined_name, combined_files))
                modules.sort(key=lambda x: len(x[1]))
        
        for module_name, module_files in modules:
            prs.append({
                "index": pr_index,
                "name": module_name,
                "branch_name": f"{branch_prefix}-{module_name.replace('/', '-')}",
                "title": f"{title_prefix}: {module_name} module",
                "files": [f["path"] for f in module_files],
                "description": f"Implementation of {module_name} module",
                "depends_on": [1] if pr_index > 1 else []
            })
            pr_index += 1
        
        return prs
    
    def _split_pr_by_type(self, categorized: Dict, target_count: int,
                          branch_prefix: str, title_prefix: str) -> List[Dict]:
        """Split files by type (configs -> code -> docs)."""
        prs = []
        pr_index = 1
        
        # PR1: Configs
        if categorized["configs"]:
            prs.append({
                "index": pr_index,
                "name": "configs",
                "branch_name": f"{branch_prefix}-configs",
                "title": f"{title_prefix}: Configuration files",
                "files": [f["path"] for f in categorized["configs"]],
                "description": "Configuration and setup files",
                "depends_on": []
            })
            pr_index += 1
        
        # Middle PRs: Code modules
        all_code_files = []
        for module_files in categorized["modules"].values():
            all_code_files.extend(module_files)
        all_code_files.extend(categorized["other"])
        
        if all_code_files:
            # Split code files into batches
            code_pr_count = max(1, target_count - 2)  # Reserve for configs and docs
            batch_size = max(1, len(all_code_files) // code_pr_count)
            
            for i in range(0, len(all_code_files), batch_size):
                batch = all_code_files[i:i+batch_size]
                if batch:
                    prs.append({
                        "index": pr_index,
                        "name": f"code-batch-{pr_index}",
                        "branch_name": f"{branch_prefix}-code-{pr_index}",
                        "title": f"{title_prefix}: Code batch {pr_index - 1}",
                        "files": [f["path"] for f in batch],
                        "description": f"Code implementation batch {pr_index - 1}",
                        "depends_on": [1] if pr_index > 1 else []
                    })
                    pr_index += 1
        
        # Last PR: Docs
        if categorized["docs"]:
            prs.append({
                "index": pr_index,
                "name": "docs",
                "branch_name": f"{branch_prefix}-docs",
                "title": f"{title_prefix}: Documentation",
                "files": [f["path"] for f in categorized["docs"]],
                "description": "Documentation files",
                "depends_on": list(range(1, pr_index))
            })
        
        return prs
    
    def _split_pr_balanced(self, files: List[Dict], target_count: int,
                           branch_prefix: str, title_prefix: str) -> List[Dict]:
        """Split files balancing lines of code."""
        # Sort files by lines (descending)
        sorted_files = sorted(files, key=lambda x: x.get("lines", 0), reverse=True)
        
        # Use greedy bin packing
        prs = [{"files": [], "lines": 0} for _ in range(target_count)]
        
        for f in sorted_files:
            # Find bin with minimum lines
            min_bin = min(prs, key=lambda x: x["lines"])
            min_bin["files"].append(f)
            min_bin["lines"] += f.get("lines", 1)
        
        # Convert to PR format
        result = []
        for i, pr in enumerate(prs, 1):
            if pr["files"]:
                result.append({
                    "index": i,
                    "name": f"batch-{i}",
                    "branch_name": f"{branch_prefix}-batch-{i}",
                    "title": f"{title_prefix}: Batch {i} (~{pr['lines']} lines)",
                    "files": [f["path"] for f in pr["files"]],
                    "description": f"Balanced batch {i} with approximately {pr['lines']} lines",
                    "depends_on": [j for j in range(1, i)]
                })
        
        return result
    
    def _split_pr_by_file(self, files: List[Dict], target_count: int,
                          branch_prefix: str, title_prefix: str) -> List[Dict]:
        """Split files evenly across PRs."""
        batch_size = max(1, len(files) // target_count)
        
        prs = []
        for i in range(0, len(files), batch_size):
            batch = files[i:i+batch_size]
            pr_index = len(prs) + 1
            
            if batch:
                prs.append({
                    "index": pr_index,
                    "name": f"part-{pr_index}",
                    "branch_name": f"{branch_prefix}-part-{pr_index}",
                    "title": f"{title_prefix}: Part {pr_index}/{target_count}",
                    "files": [f["path"] for f in batch],
                    "description": f"Part {pr_index} of {target_count}",
                    "depends_on": [j for j in range(1, pr_index)]
                })
        
        return prs

    def _register_tools(self):
        """Register all MCP tools."""
        
        @self.mcp.tool()
        async def analyze_code_structure(
            source_path: str,
            include_patterns: Optional[List[str]] = None,
            exclude_patterns: Optional[List[str]] = None
        ) -> Dict[str, Any]:
            """
            Analyze the code structure of a directory.
            
            Args:
                source_path: Path to the source directory to analyze
                include_patterns: Optional list of glob patterns to include (e.g., ["*.py", "*.js"])
                exclude_patterns: Optional list of glob patterns to exclude
                
            Returns:
                Analysis result containing:
                - modules: Detected modules/directories with file counts
                - files: List of all files with metadata (path, lines, imports)
                - dependencies: Dependency graph between files
                - summary: Statistics about the codebase
            """
            logger.info(f"Analyzing code structure: {source_path}")
            self.stats["analyses_performed"] += 1
            
            result = self.analyzer.analyze(
                source_path=source_path,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns
            )
            
            return result
        
        @self.mcp.tool()
        async def generate_split_plan(
            source_path: str,
            target_pr_count: int = 8,
            strategy: str = "by_module",
            base_branch: str = "main",
            branch_prefix: str = "user/feature"
        ) -> Dict[str, Any]:
            """
            Generate an intelligent split plan for dividing code into multiple PRs.
            
            Args:
                source_path: Path to the source directory
                target_pr_count: Target number of PRs to create (default: 8)
                strategy: Split strategy - one of:
                    - "by_module": Split by top-level modules/directories
                    - "by_file": Split by individual files
                    - "by_type": Split by file type (config, code, docs)
                    - "balanced": Balance lines of code across PRs
                base_branch: Base branch name for the feature (default: "main")
                branch_prefix: Prefix for generated branch names (e.g., "user/name/feature")
                
            Returns:
                Split plan containing:
                - prs: List of PR definitions with files and descriptions
                - summary: Statistics about the split
                - dependency_order: Recommended merge order
            """
            logger.info(f"Generating split plan: {source_path} -> {target_pr_count} PRs")
            self.stats["plans_generated"] += 1
            
            result = self.planner.generate_plan(
                source_path=source_path,
                target_pr_count=target_pr_count,
                strategy=strategy,
                base_branch=base_branch,
                branch_prefix=branch_prefix
            )
            
            return result
        
        @self.mcp.tool()
        async def execute_split(
            plan: Dict[str, Any],
            source_path: str,
            target_repo_path: str,
            dry_run: bool = True
        ) -> Dict[str, Any]:
            """
            Execute a split plan by creating branches, copying files, and pushing.
            
            Args:
                plan: Split plan from generate_split_plan (the "plan" field)
                source_path: Path to source files
                target_repo_path: Path to target git repository
                dry_run: If True, preview changes without executing (default: True)
                
            Returns:
                Execution result containing:
                - branches: List of created branches with commit hashes
                - summary: Success/failure statistics
                - status: Overall execution status
            """
            logger.info(f"Executing split: {source_path} -> {target_repo_path} (dry_run={dry_run})")
            
            if not dry_run:
                self.stats["splits_executed"] += 1
            
            self.git_manager.repo_path = Path(target_repo_path).absolute()
            
            result = self.git_manager.execute_split(
                plan=plan,
                source_path=source_path,
                target_repo_path=target_repo_path,
                dry_run=dry_run
            )
            
            return result
        
        @self.mcp.tool()
        async def get_split_strategies() -> Dict[str, Any]:
            """
            Get available split strategies and their descriptions.
            
            Returns:
                Dictionary of available strategies with descriptions and use cases.
            """
            return {
                "strategies": {
                    "by_module": {
                        "name": "By Module",
                        "description": "Split by top-level modules/directories",
                        "use_case": "Best for well-organized codebases with clear module boundaries",
                        "example": "models/, utils/, configs/ each become separate PRs"
                    },
                    "by_file": {
                        "name": "By File",
                        "description": "Distribute files evenly across PRs",
                        "use_case": "When you need exactly N PRs regardless of structure",
                        "example": "10 files / 5 PRs = 2 files per PR"
                    },
                    "by_type": {
                        "name": "By Type",
                        "description": "Split by file type (configs first, then code, then docs)",
                        "use_case": "When dependency order matters (configs before code)",
                        "example": "PR1: configs, PR2-7: code batches, PR8: docs"
                    },
                    "balanced": {
                        "name": "Balanced",
                        "description": "Balance lines of code across PRs",
                        "use_case": "When you want roughly equal review effort per PR",
                        "example": "1000 lines / 5 PRs = ~200 lines per PR"
                    }
                },
                "workflow": {
                    "description": "Recommended workflow with coding-flow MCP",
                    "steps": [
                        "1. coding-flow.get_pr_content(prIdOrUrl) - Get PR files and changes",
                        "2. pr-splitter.generate_split_plan_from_pr(pr_data) - Generate split plan",
                        "3. Git operations: create branches, cherry-pick files",
                        "4. coding-flow.create_draft_pr() for each sub-PR"
                    ]
                }
            }
        
        @self.mcp.tool()
        async def generate_split_plan_from_pr(
            pr_files: list,
            target_pr_count: int = 5,
            strategy: str = "by_module",
            base_branch: str = "main",
            branch_prefix: str = "user/feature",
            pr_title_prefix: str = "Split PR"
        ) -> Dict[str, Any]:
            """
            Generate a split plan directly from PR file data (from coding-flow.get_pr_content).
            
            This is the recommended tool to use with coding-flow MCP:
            1. Call coding-flow.get_pr_content(prIdOrUrl) to get PR data
            2. Pass the changedFiles to this tool
            3. Use the generated plan to create branches and PRs
            
            Args:
                pr_files: List of PR files from coding-flow.get_pr_content()
                    Each file should have: path, changeType (add/edit/delete), 
                    Optional: additions, deletions
                target_pr_count: Target number of PRs to create (default: 5)
                strategy: Split strategy - by_module, by_file, by_type, balanced
                base_branch: Base branch for the split PRs
                branch_prefix: Prefix for generated branch names
                pr_title_prefix: Prefix for PR titles (e.g., "[Feature 1/5]")
                
            Returns:
                Split plan with:
                - prs: List of PR definitions (files, title, branch, description)
                - summary: Statistics
                - merge_order: Recommended merge sequence
            """
            logger.info(f"Generating split plan from PR data: {len(pr_files)} files -> {target_pr_count} PRs")
            self.stats["plans_generated"] += 1
            
            # Convert PR files to internal format
            files_info = []
            for f in pr_files:
                path = f.get("path", f.get("filePath", ""))
                files_info.append({
                    "path": path,
                    "change_type": f.get("changeType", "edit"),
                    "additions": f.get("additions", 0),
                    "deletions": f.get("deletions", 0),
                    "lines": f.get("additions", 0) + f.get("deletions", 0)
                })
            
            # Categorize files
            categorized = self._categorize_files(files_info)
            
            # Generate plan based on strategy
            prs = []
            
            if strategy == "by_module":
                prs = self._split_pr_by_module(categorized, target_pr_count, branch_prefix, pr_title_prefix)
            elif strategy == "by_type":
                prs = self._split_pr_by_type(categorized, target_pr_count, branch_prefix, pr_title_prefix)
            elif strategy == "balanced":
                prs = self._split_pr_balanced(files_info, target_pr_count, branch_prefix, pr_title_prefix)
            else:  # by_file
                prs = self._split_pr_by_file(files_info, target_pr_count, branch_prefix, pr_title_prefix)
            
            # Calculate summary
            total_files = len(files_info)
            total_lines = sum(f.get("lines", 0) for f in files_info)
            
            return {
                "status": "success",
                "plan": {
                    "target_pr_count": target_pr_count,
                    "actual_pr_count": len(prs),
                    "strategy": strategy,
                    "base_branch": base_branch,
                    "branch_prefix": branch_prefix,
                    "prs": prs
                },
                "summary": {
                    "total_files": total_files,
                    "total_lines": total_lines,
                    "files_per_pr": total_files / len(prs) if prs else 0,
                    "lines_per_pr": total_lines / len(prs) if prs else 0
                },
                "merge_order": [pr["index"] for pr in prs],
                "workflow_next_steps": [
                    f"1. Create base branch '{base_branch}' if not exists",
                    "2. For each PR in plan:",
                    f"   a. git checkout -b <branch_name> {base_branch}",
                    "   b. git checkout <source_branch> -- <files>",
                    "   c. git commit -m '<pr_title>'",
                    "   d. git push -u origin <branch_name>",
                    f"3. Use coding-flow.create_draft_pr() for each branch targeting '{base_branch}'"
                ]
            }
        
        @self.mcp.tool()
        async def generate_pr_descriptions(
            plan: Dict[str, Any],
            project_name: str = "Project",
            include_dependencies: bool = True
        ) -> Dict[str, Any]:
            """
            Generate detailed PR titles and descriptions for a split plan.
            
            This tool enhances a split plan with professional PR descriptions
            ready for use with coding-flow.create_draft_pr().
            
            Args:
                plan: Split plan from generate_split_plan_from_pr
                project_name: Name of the project for PR titles
                include_dependencies: Include dependency info in descriptions
                
            Returns:
                Enhanced plan with detailed titles and descriptions for each PR.
            """
            prs = plan.get("prs", [])
            total = len(prs)
            enhanced_prs = []
            
            for pr in prs:
                idx = pr.get("index", 1)
                files = pr.get("files", [])
                
                # Generate title
                title = f"[{project_name} {idx}/{total}] {pr.get('title', pr.get('name', 'Update'))}"
                
                # Generate description
                file_list = "\n".join([f"- `{f}`" for f in files[:10]])
                if len(files) > 10:
                    file_list += f"\n- ... and {len(files) - 10} more files"
                
                description = f"""## Summary
{pr.get('description', 'Part of a split PR series.')}

### Files Changed ({len(files)} files)
{file_list}

"""
                if include_dependencies and pr.get("depends_on"):
                    deps = pr.get("depends_on", [])
                    description += f"""### Dependencies
This PR depends on PR(s): {', '.join([f'{d}/{total}' for d in deps])}

"""
                
                description += f"""### Review Focus
- Code correctness
- Integration points with other parts

---
*Generated by PR-Splitter-MCP*"""
                
                enhanced_prs.append({
                    **pr,
                    "title": title,
                    "description": description
                })
            
            return {
                "status": "success",
                "prs": enhanced_prs,
                "ready_for_creation": True,
                "usage": "Pass each PR to coding-flow.create_draft_pr() with title and description"
            }
        
        @self.mcp.tool()
        async def get_server_stats() -> Dict[str, Any]:
            """
            Get server statistics.
            
            Returns:
                Server statistics including uptime and operation counts.
            """
            uptime = datetime.now() - self.stats["start_time"]
            return {
                "uptime_seconds": uptime.total_seconds(),
                "uptime_formatted": str(uptime),
                "analyses_performed": self.stats["analyses_performed"],
                "plans_generated": self.stats["plans_generated"],
                "splits_executed": self.stats["splits_executed"],
                "prs_created": self.stats["prs_created"]
            }
        
        @self.mcp.tool()
        async def check_auth_status() -> Dict[str, Any]:
            """
            Check authentication and dependency status for PR creation.
            
            This tool verifies:
            - Azure DevOps: AzureCliCredential (from `az login`)
            - GitHub: Token from gh auth or GITHUB_TOKEN env var
            - Required Python packages
            
            Returns:
                Comprehensive status of authentication and dependencies.
            """
            ado_status = self.pr_creator.check_ado_auth()
            github_status = self.pr_creator.check_github_auth()
            deps_status = self.pr_creator.check_dependencies()
            
            return {
                "azure_devops": {
                    "authenticated": ado_status.get("available", False),
                    "method": ado_status.get("method"),
                    "message": ado_status.get("message") or ado_status.get("error"),
                    "how_to_fix": ado_status.get("how_to_fix")
                },
                "github": {
                    "authenticated": github_status.get("available", False),
                    "method": github_status.get("method"),
                    "message": github_status.get("message") or github_status.get("error"),
                    "how_to_fix": github_status.get("how_to_fix")
                },
                "dependencies": deps_status,
                "ready": {
                    "ado": ado_status.get("available", False) and deps_status.get("installed", {}).get("azure-devops", False),
                    "github": github_status.get("available", False) and deps_status.get("installed", {}).get("PyGithub", False)
                }
            }
        
        @self.mcp.tool()
        async def create_ado_pr(
            org_url: str,
            project: str,
            repo: str,
            source_branch: str,
            target_branch: str,
            title: str,
            description: str = "",
            draft: bool = True,
            work_item_id: Optional[str] = None
        ) -> Dict[str, Any]:
            """
            Create a Pull Request in Azure DevOps using native SDK.
            
            Authentication: Uses AzureCliCredential (from `az login`).
            Same authentication pattern as coding-flow - no manual token needed!
            
            Args:
                org_url: Azure DevOps organization URL (e.g., https://dev.azure.com/your-org)
                project: Project name
                repo: Repository name
                source_branch: Source branch name
                target_branch: Target branch name
                title: PR title
                description: PR description (optional)
                draft: Create as draft PR (default: True)
                work_item_id: Optional ADO work item ID to link
                
            Returns:
                PR creation result with PR ID and URL.
            """
            logger.info(f"Creating ADO PR: {source_branch} -> {target_branch}")
            
            result = self.pr_creator.create_ado_pr(
                org_url=org_url,
                project=project,
                repo=repo,
                source_branch=source_branch,
                target_branch=target_branch,
                title=title,
                description=description,
                draft=draft,
                work_item_id=work_item_id
            )
            
            if result.status == "success":
                self.stats["prs_created"] += 1
            
            return result.to_dict()
        
        @self.mcp.tool()
        async def create_github_pr(
            repo: str,
            source_branch: str,
            target_branch: str = "main",
            title: str = "",
            body: str = "",
            draft: bool = True
        ) -> Dict[str, Any]:
            """
            Create a Pull Request in GitHub using native SDK.
            
            Authentication: Uses token from `gh auth login` or GITHUB_TOKEN env var.
            Same authentication pattern as coding-flow - no manual token needed!
            
            Args:
                repo: Repository in format "owner/repo"
                source_branch: Source branch name
                target_branch: Target branch name (default: main)
                title: PR title (default: branch name)
                body: PR body/description (optional)
                draft: Create as draft PR (default: True)
                
            Returns:
                PR creation result with PR ID and URL.
            """
            logger.info(f"Creating GitHub PR: {source_branch} -> {target_branch}")
            
            result = self.pr_creator.create_github_pr(
                repo=repo,
                source_branch=source_branch,
                target_branch=target_branch,
                title=title,
                body=body,
                draft=draft
            )
            
            if result.status == "success":
                self.stats["prs_created"] += 1
            
            return result.to_dict()
        
        @self.mcp.tool()
        async def split_folder_to_plan(
            folder_path: str,
            target_pr_count: int = 5,
            strategy: str = "by_module",
            base_branch: str = "main",
            branch_prefix: str = "user/feature",
            pr_title_prefix: str = "Split PR",
            include_patterns: Optional[List[str]] = None,
            exclude_patterns: Optional[List[str]] = None
        ) -> Dict[str, Any]:
            """
            Generate a split plan from a local folder (similar to generate_split_plan_from_pr).
            
            This tool analyzes a local folder and generates a split plan that can be
            used with execute_split or manual git operations.
            
            Args:
                folder_path: Path to the folder containing code to split
                target_pr_count: Target number of PRs to create (default: 5)
                strategy: Split strategy - by_module, by_file, by_type, balanced
                base_branch: Base branch for the split PRs
                branch_prefix: Prefix for generated branch names
                pr_title_prefix: Prefix for PR titles
                include_patterns: File patterns to include (e.g., ["*.py", "*.js"])
                exclude_patterns: File patterns to exclude (e.g., ["__pycache__/*"])
                
            Returns:
                Split plan with:
                - prs: List of PR definitions (files, title, branch, description)
                - summary: Statistics
                - workflow_next_steps: Instructions for next steps
            """
            logger.info(f"Generating split plan from folder: {folder_path} -> {target_pr_count} PRs")
            self.stats["plans_generated"] += 1
            
            folder = Path(folder_path)
            if not folder.exists():
                return {"status": "error", "message": f"Folder not found: {folder_path}"}
            
            # Collect all files
            files_info = []
            
            # Default exclude patterns
            default_excludes = [
                '__pycache__', '.git', '.venv', 'venv', 'node_modules',
                '.pytest_cache', '.mypy_cache', '*.pyc', '*.pyo', '.DS_Store'
            ]
            all_excludes = (exclude_patterns or []) + default_excludes
            
            for file_path in folder.rglob('*'):
                if file_path.is_file():
                    # Get relative path
                    rel_path = str(file_path.relative_to(folder))
                    
                    # Check excludes
                    skip = False
                    for pattern in all_excludes:
                        if pattern in rel_path or file_path.match(pattern):
                            skip = True
                            break
                    if skip:
                        continue
                    
                    # Check includes (if specified)
                    if include_patterns:
                        include = False
                        for pattern in include_patterns:
                            if file_path.match(pattern):
                                include = True
                                break
                        if not include:
                            continue
                    
                    # Count lines
                    try:
                        lines = len(file_path.read_text(encoding='utf-8', errors='ignore').splitlines())
                    except:
                        lines = 0
                    
                    files_info.append({
                        "path": rel_path,
                        "change_type": "add",
                        "lines": lines,
                        "additions": lines,
                        "deletions": 0
                    })
            
            if not files_info:
                return {"status": "error", "message": "No files found in folder"}
            
            # Categorize files
            categorized = self._categorize_files(files_info)
            
            # Generate plan based on strategy
            prs = []
            
            if strategy == "by_module":
                prs = self._split_pr_by_module(categorized, target_pr_count, branch_prefix, pr_title_prefix)
            elif strategy == "by_type":
                prs = self._split_pr_by_type(categorized, target_pr_count, branch_prefix, pr_title_prefix)
            elif strategy == "balanced":
                prs = self._split_pr_balanced(files_info, target_pr_count, branch_prefix, pr_title_prefix)
            else:  # by_file
                prs = self._split_pr_by_file(files_info, target_pr_count, branch_prefix, pr_title_prefix)
            
            total_files = len(files_info)
            total_lines = sum(f.get("lines", 0) for f in files_info)
            
            return {
                "status": "success",
                "source_folder": str(folder_path),
                "plan": {
                    "target_pr_count": target_pr_count,
                    "actual_pr_count": len(prs),
                    "strategy": strategy,
                    "base_branch": base_branch,
                    "branch_prefix": branch_prefix,
                    "prs": prs
                },
                "summary": {
                    "total_files": total_files,
                    "total_lines": total_lines,
                    "files_per_pr": round(total_files / len(prs), 1) if prs else 0,
                    "lines_per_pr": round(total_lines / len(prs), 1) if prs else 0
                },
                "merge_order": [pr["index"] for pr in prs],
                "workflow_next_steps": [
                    f"1. Ensure target repo has base branch '{base_branch}'",
                    "2. Use execute_split(plan, source_folder, target_repo, dry_run=False) to create branches",
                    "3. Or use split_and_push_folder() for end-to-end automation",
                    "4. Use create_prs_from_plan() or coding-flow.create_draft_pr() to create PRs"
                ]
            }
        
        @self.mcp.tool()
        async def split_and_push_folder(
            source_folder: str,
            target_repo_path: str,
            target_pr_count: int = 5,
            strategy: str = "by_module",
            base_branch: str = "main",
            branch_prefix: str = "user/feature",
            pr_title_prefix: str = "Split PR",
            relative_path_in_repo: str = "",
            include_patterns: Optional[List[str]] = None,
            exclude_patterns: Optional[List[str]] = None,
            dry_run: bool = True,
            push: bool = True
        ) -> Dict[str, Any]:
            """
            End-to-end: Analyze folder, create split plan, create branches, and push.
            
            This is the all-in-one tool for splitting a local folder into multiple PRs.
            After running this, you can use create_prs_from_plan() or coding-flow to create the actual PRs.
            
            Args:
                source_folder: Path to the folder containing code to split
                target_repo_path: Path to the target git repository
                target_pr_count: Target number of PRs to create (default: 5)
                strategy: Split strategy - by_module, by_file, by_type, balanced
                base_branch: Base branch in target repo (will be created if not exists)
                branch_prefix: Prefix for generated branch names
                pr_title_prefix: Prefix for PR titles
                relative_path_in_repo: Where to put files in the target repo (e.g., "src/feature/")
                include_patterns: File patterns to include
                exclude_patterns: File patterns to exclude
                dry_run: If True, preview without making changes (default: True)
                push: If True, push branches to remote (default: True)
                
            Returns:
                Complete result including:
                - plan: The split plan used
                - branches: Created branches with status
                - next_steps: How to create the PRs
            """
            logger.info(f"Split and push: {source_folder} -> {target_repo_path} ({target_pr_count} PRs)")
            
            source = Path(source_folder)
            target = Path(target_repo_path)
            
            if not source.exists():
                return {"status": "error", "message": f"Source folder not found: {source_folder}"}
            
            if not target.exists():
                return {"status": "error", "message": f"Target repo not found: {target_repo_path}"}
            
            # Check if target is a git repo
            if not self.git_manager.is_git_repo(str(target)):
                return {"status": "error", "message": f"Target is not a git repository: {target_repo_path}"}
            
            self.git_manager.repo_path = target.absolute()
            
            # Step 1: Generate split plan
            plan_result = await split_folder_to_plan(
                folder_path=source_folder,
                target_pr_count=target_pr_count,
                strategy=strategy,
                base_branch=base_branch,
                branch_prefix=branch_prefix,
                pr_title_prefix=pr_title_prefix,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns
            )
            
            if plan_result.get("status") != "success":
                return plan_result
            
            plan = plan_result["plan"]
            
            # Adjust file paths if relative_path_in_repo is specified
            if relative_path_in_repo:
                for pr in plan["prs"]:
                    pr["files"] = [os.path.join(relative_path_in_repo, f) for f in pr["files"]]
            
            if dry_run:
                return {
                    "status": "success",
                    "dry_run": True,
                    "plan": plan,
                    "summary": plan_result["summary"],
                    "message": "Dry run complete. Set dry_run=False to execute.",
                    "branches_to_create": [pr["branch_name"] for pr in plan["prs"]],
                    "next_steps": [
                        "Review the plan above",
                        "Run again with dry_run=False to create branches",
                        "Then use create_prs_from_plan() or coding-flow.create_draft_pr()"
                    ]
                }
            
            # Step 2: Execute split (create branches, copy files, commit, optionally push)
            self.stats["splits_executed"] += 1
            
            # Ensure base branch exists
            current_branch = self.git_manager.get_current_branch()
            checkout_result = self.git_manager.checkout(base_branch)
            
            if checkout_result.get("status") == "error":
                # Try to create base branch from main/master
                for fallback in ["main", "master", current_branch]:
                    result = self.git_manager.create_branch(base_branch, fallback)
                    if result.get("status") == "success":
                        if push:
                            self.git_manager.push(base_branch)
                        break
            
            branch_results = []
            
            for pr in plan["prs"]:
                branch_name = pr["branch_name"]
                files = pr["files"]
                title = pr.get("title", pr.get("description", "Update"))
                
                # Create branch from base
                branch_result = self.git_manager.create_branch(branch_name, base_branch)
                if branch_result.get("status") == "error":
                    branch_results.append({
                        "branch_name": branch_name,
                        "status": "error",
                        "error": branch_result.get("message")
                    })
                    continue
                
                # Copy files from source to target
                copied_files = []
                for file_path in files:
                    # Handle relative_path_in_repo
                    if relative_path_in_repo:
                        src_rel = file_path.replace(relative_path_in_repo, "").lstrip("/")
                    else:
                        src_rel = file_path
                    
                    src_file = source / src_rel
                    dst_file = target / file_path
                    
                    if src_file.exists():
                        dst_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_file, dst_file)
                        copied_files.append(file_path)
                
                if not copied_files:
                    branch_results.append({
                        "branch_name": branch_name,
                        "status": "warning",
                        "files_copied": 0,
                        "error": "No files copied"
                    })
                    self.git_manager.checkout(base_branch)
                    continue
                
                # Add, commit
                self.git_manager.add_files(copied_files)
                commit_result = self.git_manager.commit(f"feat: {title}")
                
                # Push if requested
                push_result = {"status": "skipped"}
                if push:
                    push_result = self.git_manager.push(branch_name)
                
                branch_results.append({
                    "branch_name": branch_name,
                    "status": "success" if push_result.get("status") in ["success", "skipped"] else "partial",
                    "files_copied": len(copied_files),
                    "commit_hash": commit_result.get("commit_hash"),
                    "pushed": push_result.get("status") == "success"
                })
                
                # Return to base branch
                self.git_manager.checkout(base_branch)
            
            return {
                "status": "success",
                "dry_run": False,
                "source_folder": str(source_folder),
                "target_repo": str(target_repo_path),
                "relative_path": relative_path_in_repo,
                "plan": plan,
                "summary": plan_result["summary"],
                "branches": branch_results,
                "branch_summary": {
                    "total": len(branch_results),
                    "successful": len([b for b in branch_results if b["status"] == "success"]),
                    "failed": len([b for b in branch_results if b["status"] == "error"])
                },
                "next_steps": [
                    "Use create_prs_from_plan(plan, platform, repo, ...) to create all PRs",
                    "Or use coding-flow.create_draft_pr() for each branch individually",
                    f"Target each PR to branch: {base_branch}"
                ]
            }
        
        @self.mcp.tool()
        async def create_prs_from_plan(
            plan: Dict[str, Any],
            platform: str,
            repo: str,
            org_url: Optional[str] = None,
            project: Optional[str] = None,
            draft: bool = True
        ) -> Dict[str, Any]:
            """
            Batch create PRs from a split plan.
            
            This tool takes a split plan (from generate_split_plan) and creates
            all the PRs automatically on the specified platform.
            
            Authentication: Uses system credentials (az login / gh auth login).
            
            Args:
                plan: Split plan from generate_split_plan (use the "plan" field)
                platform: Target platform - "ado" for Azure DevOps or "github" for GitHub
                repo: Repository name
                    - For GitHub: format "owner/repo" (e.g., "Polly2014/MyRepo")
                    - For ADO: just repo name (e.g., "xpaytools")
                org_url: Azure DevOps org URL (required for ADO, e.g., https://msasg.visualstudio.com)
                project: Azure DevOps project name (required for ADO, e.g., XPay)
                draft: Create as draft PRs (default: True)
                
            Returns:
                Batch creation results with PR URLs and any errors.
            """
            logger.info(f"Creating PRs from plan on {platform}")
            
            result = self.pr_creator.create_prs_from_plan(
                plan=plan,
                platform=platform,
                org_url=org_url,
                project=project,
                repo=repo,
                draft=draft
            )
            
            self.stats["prs_created"] += result.get("prs_created", 0)
            
            return result
    
    def run(self):
        """Run the MCP server."""
        logger.info("Starting PR-Splitter MCP Server...")
        self.mcp.run()


def main():
    """Main entry point."""
    server = PRSplitterMCPServer()
    server.run()


if __name__ == "__main__":
    main()
