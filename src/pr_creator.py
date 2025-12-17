"""
PR Creator - Professional SDK Implementation
Handles PR creation for Azure DevOps and GitHub using native SDKs.
Uses system credentials (AzureCliCredential, gh auth token) - no manual token configuration needed.

Authentication Flow (same as coding-flow):
- Azure DevOps: AzureCliCredential → InteractiveBrowserCredential (fallback)
- GitHub: gh auth token → GITHUB_TOKEN env var (fallback)
"""

import os
import subprocess
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


def _get_github_token() -> Optional[str]:
    """
    Get GitHub token using the same pattern as coding-flow:
    1. Try GITHUB_PAT_TOKEN env var
    2. Try GITHUB_TOKEN env var  
    3. Try `gh auth token` command
    """
    # Check environment variables first
    token = os.environ.get("GITHUB_PAT_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        logger.debug("Using GitHub token from environment variable")
        return token
    
    # Try gh CLI
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            logger.debug("Using GitHub token from gh auth")
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    
    return None


class PRPlatform(Enum):
    """Supported PR platforms."""
    AZURE_DEVOPS = "ado"
    GITHUB = "github"


@dataclass
class PRResult:
    """Result of a PR creation operation."""
    platform: str
    pr_id: Optional[str]
    pr_url: Optional[str]
    status: str
    branch_name: str
    title: str
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "pr_id": self.pr_id,
            "pr_url": self.pr_url,
            "status": self.status,
            "branch_name": self.branch_name,
            "title": self.title,
            "error": self.error
        }


class AzureDevOpsClient:
    """
    Azure DevOps client using azure-devops SDK with AzureCliCredential.
    No manual PAT configuration required - uses `az login` credentials.
    
    Authentication chain (same as coding-flow):
    1. AzureCliCredential - uses token from `az login`
    2. InteractiveBrowserCredential - prompts browser login if needed
    """
    
    # Azure DevOps resource ID for token scope
    ADO_RESOURCE_ID = "499b84ac-1321-427f-aa17-267ca6975798/.default"
    
    def __init__(self, org_url: str):
        self.org_url = org_url.rstrip('/')
        self._connection = None
        self._git_client = None
    
    def _get_connection(self):
        """Get or create ADO connection using Azure CLI credentials."""
        if self._connection is not None:
            return self._connection
        
        try:
            from azure.devops.connection import Connection
            from azure.identity import ChainedTokenCredential, AzureCliCredential, InteractiveBrowserCredential
            from msrest.authentication import BasicTokenAuthentication
            
            # Same pattern as coding-flow: try CLI first, then browser
            credential = ChainedTokenCredential(
                AzureCliCredential(),
                InteractiveBrowserCredential()
            )
            
            # Get token for Azure DevOps
            token = credential.get_token(self.ADO_RESOURCE_ID)
            
            # Create connection with the token
            credentials = BasicTokenAuthentication({'access_token': token.token})
            self._connection = Connection(base_url=self.org_url, creds=credentials)
            
            return self._connection
        except ImportError as e:
            raise ImportError(
                "Required packages not installed. Run:\n"
                "pip install azure-devops azure-identity msrest"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to authenticate with Azure DevOps: {e}") from e
    
    def _get_git_client(self):
        """Get Git client."""
        if self._git_client is not None:
            return self._git_client
        
        connection = self._get_connection()
        self._git_client = connection.clients.get_git_client()
        return self._git_client
    
    def create_pull_request(
        self,
        project: str,
        repo: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str = "",
        draft: bool = True,
        work_item_ids: Optional[List[int]] = None
    ) -> PRResult:
        """Create a pull request in Azure DevOps."""
        try:
            from azure.devops.v7_0.git.models import (
                GitPullRequest,
                ResourceRef
            )
            
            git_client = self._get_git_client()
            
            # Ensure branch refs format
            if not source_branch.startswith("refs/heads/"):
                source_branch_ref = f"refs/heads/{source_branch}"
            else:
                source_branch_ref = source_branch
                source_branch = source_branch.replace("refs/heads/", "")
                
            if not target_branch.startswith("refs/heads/"):
                target_branch_ref = f"refs/heads/{target_branch}"
            else:
                target_branch_ref = target_branch
            
            # Create PR object
            pr = GitPullRequest(
                source_ref_name=source_branch_ref,
                target_ref_name=target_branch_ref,
                title=title,
                description=description,
                is_draft=draft
            )
            
            # Add work item links if provided
            if work_item_ids:
                pr.work_item_refs = [
                    ResourceRef(id=str(wi_id)) for wi_id in work_item_ids
                ]
            
            # Create the PR
            created_pr = git_client.create_pull_request(pr, repo, project)
            
            # Build PR URL
            pr_url = f"{self.org_url}/{project}/_git/{repo}/pullrequest/{created_pr.pull_request_id}"
            
            logger.info(f"Created ADO PR #{created_pr.pull_request_id}: {pr_url}")
            
            return PRResult(
                platform="ado",
                pr_id=str(created_pr.pull_request_id),
                pr_url=pr_url,
                status="success",
                branch_name=source_branch,
                title=title
            )
            
        except Exception as e:
            logger.error(f"Failed to create ADO PR: {e}")
            return PRResult(
                platform="ado",
                pr_id=None,
                pr_url=None,
                status="error",
                branch_name=source_branch,
                title=title,
                error=str(e)
            )


class GitHubClient:
    """
    GitHub client using PyGithub SDK.
    
    Token resolution order (same as coding-flow):
    1. GITHUB_PAT_TOKEN env var
    2. GITHUB_TOKEN env var
    3. `gh auth token` command output
    
    No manual configuration required if `gh auth login` was done.
    """
    
    def __init__(self):
        self._github = None
        self._token = None
    
    def _get_client(self):
        """Get or create GitHub client."""
        if self._github is not None:
            return self._github
        
        self._token = _get_github_token()
        if not self._token:
            raise RuntimeError(
                "GitHub authentication not found. Either:\n"
                "1. Run: gh auth login\n"
                "2. Set GITHUB_TOKEN environment variable"
            )
        
        try:
            from github import Github
            self._github = Github(self._token)
            return self._github
        except ImportError:
            raise ImportError("PyGithub not installed. Run: pip install PyGithub")
    
    def create_pull_request(
        self,
        repo: str,
        source_branch: str,
        target_branch: str = "main",
        title: str = "",
        body: str = "",
        draft: bool = True
    ) -> PRResult:
        """Create a pull request in GitHub."""
        try:
            gh = self._get_client()
            repository = gh.get_repo(repo)
            
            # Create PR
            pr = repository.create_pull(
                title=title or f"PR: {source_branch}",
                body=body,
                head=source_branch,
                base=target_branch,
                draft=draft
            )
            
            logger.info(f"Created GitHub PR #{pr.number}: {pr.html_url}")
            
            return PRResult(
                platform="github",
                pr_id=str(pr.number),
                pr_url=pr.html_url,
                status="success",
                branch_name=source_branch,
                title=title or source_branch
            )
            
        except Exception as e:
            logger.error(f"Failed to create GitHub PR: {e}")
            return PRResult(
                platform="github",
                pr_id=None,
                pr_url=None,
                status="error",
                branch_name=source_branch,
                title=title or source_branch,
                error=str(e)
            )


class PRCreator:
    """
    Professional PR Creator using native SDKs.
    
    Zero-Config Authentication (same pattern as coding-flow):
    
    Azure DevOps:
      - Uses ChainedTokenCredential(AzureCliCredential, InteractiveBrowserCredential)
      - Automatically uses token from `az login`
      - Falls back to browser login if needed
    
    GitHub:
      - Checks GITHUB_PAT_TOKEN env var
      - Checks GITHUB_TOKEN env var  
      - Falls back to `gh auth token` command
    
    No manual token configuration required!
    """
    
    def __init__(self):
        """Initialize PRCreator."""
        self._ado_clients: Dict[str, AzureDevOpsClient] = {}
        self._github_client: Optional[GitHubClient] = None
    
    def _get_ado_client(self, org_url: str) -> AzureDevOpsClient:
        """Get or create ADO client for an organization."""
        if org_url not in self._ado_clients:
            self._ado_clients[org_url] = AzureDevOpsClient(org_url)
        return self._ado_clients[org_url]
    
    def _get_github_client(self) -> GitHubClient:
        """Get or create GitHub client."""
        if self._github_client is None:
            self._github_client = GitHubClient()
        return self._github_client
    
    def check_ado_auth(self) -> Dict[str, Any]:
        """
        Check if Azure DevOps authentication is available.
        
        Returns:
            Status information about ADO authentication
        """
        try:
            from azure.identity import AzureCliCredential
            credential = AzureCliCredential()
            # Try to get a token
            token = credential.get_token(AzureDevOpsClient.ADO_RESOURCE_ID)
            return {
                "available": True,
                "method": "AzureCliCredential",
                "message": "Authenticated via az login"
            }
        except ImportError:
            return {
                "available": False,
                "error": "azure-identity not installed",
                "how_to_fix": "pip install azure-identity azure-devops msrest"
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "how_to_fix": "Run: az login"
            }
    
    def check_github_auth(self) -> Dict[str, Any]:
        """
        Check if GitHub authentication is available.
        
        Returns:
            Status information about GitHub authentication
        """
        token = _get_github_token()
        if token:
            # Determine source
            if os.environ.get("GITHUB_PAT_TOKEN"):
                source = "GITHUB_PAT_TOKEN env var"
            elif os.environ.get("GITHUB_TOKEN"):
                source = "GITHUB_TOKEN env var"
            else:
                source = "gh auth token"
            
            return {
                "available": True,
                "method": source,
                "message": f"Token found via {source}"
            }
        
        return {
            "available": False,
            "error": "No GitHub token found",
            "how_to_fix": "Run: gh auth login"
        }
    
    def check_dependencies(self) -> Dict[str, Any]:
        """Check if required Python packages are installed."""
        deps = {
            "azure-identity": False,
            "azure-devops": False,
            "msrest": False,
            "PyGithub": False
        }
        
        try:
            import azure.identity
            deps["azure-identity"] = True
        except ImportError:
            pass
        
        try:
            import azure.devops
            deps["azure-devops"] = True
        except ImportError:
            pass
        
        try:
            import msrest
            deps["msrest"] = True
        except ImportError:
            pass
        
        try:
            import github
            deps["PyGithub"] = True
        except ImportError:
            pass
        
        missing = [k for k, v in deps.items() if not v]
        
        return {
            "installed": deps,
            "all_installed": len(missing) == 0,
            "missing": missing,
            "install_command": f"pip install {' '.join(missing)}" if missing else None
        }
    
    def create_ado_pr(
        self,
        org_url: str,
        project: str,
        repo: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str = "",
        draft: bool = True,
        work_item_id: Optional[str] = None
    ) -> PRResult:
        """
        Create a Pull Request in Azure DevOps using SDK.
        
        Authentication: Uses AzureCliCredential (from `az login`)
        """
        client = self._get_ado_client(org_url)
        
        work_item_ids = [int(work_item_id)] if work_item_id else None
        
        return client.create_pull_request(
            project=project,
            repo=repo,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            description=description,
            draft=draft,
            work_item_ids=work_item_ids
        )
    
    def create_github_pr(
        self,
        repo: str,
        source_branch: str,
        target_branch: str = "main",
        title: str = "",
        body: str = "",
        draft: bool = True
    ) -> PRResult:
        """
        Create a Pull Request in GitHub using SDK.
        
        Authentication: Uses gh auth token or GITHUB_TOKEN env var
        """
        client = self._get_github_client()
        
        return client.create_pull_request(
            repo=repo,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            body=body,
            draft=draft
        )
    
    def create_prs_from_plan(
        self,
        plan: Dict[str, Any],
        platform: str,
        org_url: Optional[str] = None,
        project: Optional[str] = None,
        repo: str = "",
        draft: bool = True
    ) -> Dict[str, Any]:
        """
        Batch create PRs from a split plan.
        
        Args:
            plan: Split plan from SplitPlanner
            platform: Target platform ("ado" or "github")
            org_url: Azure DevOps org URL (required for ADO)
            project: Azure DevOps project name (required for ADO)
            repo: Repository name (format: "owner/repo" for GitHub)
            draft: Create as draft PRs
            
        Returns:
            Results of PR creation
        """
        results = []
        prs = plan.get("prs", [])
        base_branch = plan.get("base_branch", "main")
        
        for pr_def in prs:
            branch_name = pr_def.get("branch_name", "")
            title = pr_def.get("name", f"PR for {branch_name}")
            description = pr_def.get("description", "")
            
            if platform == "ado":
                if not org_url or not project or not repo:
                    results.append(PRResult(
                        platform="ado",
                        pr_id=None,
                        pr_url=None,
                        status="error",
                        branch_name=branch_name,
                        title=title,
                        error="Missing required ADO parameters (org_url, project, repo)"
                    ))
                    continue
                
                result = self.create_ado_pr(
                    org_url=org_url,
                    project=project,
                    repo=repo,
                    source_branch=branch_name,
                    target_branch=base_branch,
                    title=title,
                    description=description,
                    draft=draft
                )
            elif platform == "github":
                if not repo:
                    results.append(PRResult(
                        platform="github",
                        pr_id=None,
                        pr_url=None,
                        status="error",
                        branch_name=branch_name,
                        title=title,
                        error="Missing required GitHub repo parameter (format: owner/repo)"
                    ))
                    continue
                
                result = self.create_github_pr(
                    repo=repo,
                    source_branch=branch_name,
                    target_branch=base_branch,
                    title=title,
                    body=description,
                    draft=draft
                )
            else:
                results.append(PRResult(
                    platform=platform,
                    pr_id=None,
                    pr_url=None,
                    status="error",
                    branch_name=branch_name,
                    title=title,
                    error=f"Unsupported platform: {platform}. Use 'ado' or 'github'"
                ))
                continue
            
            results.append(result)
        
        # Summary
        successful = [r for r in results if r.status == "success"]
        failed = [r for r in results if r.status == "error"]
        
        return {
            "status": "success" if not failed else ("partial" if successful else "error"),
            "platform": platform,
            "prs_created": len(successful),
            "prs_failed": len(failed),
            "results": [r.to_dict() for r in results],
            "pr_urls": [r.pr_url for r in successful if r.pr_url]
        }
