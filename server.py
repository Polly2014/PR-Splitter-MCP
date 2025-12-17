"""
PR-Splitter-MCP Server
A FastMCP-based server for intelligently splitting large PRs into smaller ones.
"""

import asyncio
import logging
import os
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
                }
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
