"""
Git Manager
Handles Git operations for creating branches, commits, and pushing.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class BranchResult:
    """Result of a branch operation."""
    branch_name: str
    status: str
    files_added: int
    commit_hash: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch_name": self.branch_name,
            "status": self.status,
            "files_added": self.files_added,
            "commit_hash": self.commit_hash,
            "error": self.error
        }


class GitManager:
    """Manages Git operations for PR splitting."""
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).absolute()
    
    def _run_git(self, *args, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """Run a git command."""
        cmd = ["git"] + list(args)
        return subprocess.run(
            cmd,
            cwd=cwd or self.repo_path,
            capture_output=True,
            text=True
        )
    
    def is_git_repo(self, path: Optional[str] = None) -> bool:
        """Check if path is a git repository."""
        check_path = Path(path) if path else self.repo_path
        result = self._run_git("rev-parse", "--git-dir", cwd=check_path)
        return result.returncode == 0
    
    def get_current_branch(self) -> str:
        """Get the current branch name."""
        result = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        return result.stdout.strip() if result.returncode == 0 else ""
    
    def get_remote_url(self, remote: str = "origin") -> str:
        """Get the remote URL."""
        result = self._run_git("remote", "get-url", remote)
        return result.stdout.strip() if result.returncode == 0 else ""
    
    def branch_exists(self, branch_name: str, remote: bool = False) -> bool:
        """Check if a branch exists."""
        if remote:
            result = self._run_git("ls-remote", "--heads", "origin", branch_name)
            return bool(result.stdout.strip())
        else:
            result = self._run_git("rev-parse", "--verify", branch_name)
            return result.returncode == 0
    
    def create_branch(self, branch_name: str, base_branch: str = "main") -> Dict[str, Any]:
        """Create a new branch from base branch."""
        # First, make sure we're on the base branch and it's up to date
        result = self._run_git("checkout", base_branch)
        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"Failed to checkout {base_branch}: {result.stderr}"
            }
        
        # Create new branch
        result = self._run_git("checkout", "-b", branch_name)
        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"Failed to create branch {branch_name}: {result.stderr}"
            }
        
        return {
            "status": "success",
            "branch_name": branch_name,
            "base_branch": base_branch
        }
    
    def add_files(self, files: List[str]) -> Dict[str, Any]:
        """Add files to staging."""
        if not files:
            return {"status": "success", "files_added": 0}
        
        result = self._run_git("add", *files)
        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"Failed to add files: {result.stderr}"
            }
        
        return {"status": "success", "files_added": len(files)}
    
    def commit(self, message: str) -> Dict[str, Any]:
        """Create a commit."""
        result = self._run_git("commit", "-m", message)
        if result.returncode != 0:
            # Check if there's nothing to commit
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                return {
                    "status": "warning",
                    "message": "Nothing to commit"
                }
            return {
                "status": "error",
                "message": f"Failed to commit: {result.stderr}"
            }
        
        # Get commit hash
        hash_result = self._run_git("rev-parse", "HEAD")
        commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else None
        
        return {
            "status": "success",
            "commit_hash": commit_hash
        }
    
    def push(self, branch_name: str, remote: str = "origin", force: bool = False) -> Dict[str, Any]:
        """Push branch to remote."""
        args = ["push", "-u", remote, branch_name]
        if force:
            args.insert(1, "--force")
        
        result = self._run_git(*args)
        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"Failed to push: {result.stderr}"
            }
        
        return {
            "status": "success",
            "branch_name": branch_name,
            "remote": remote
        }
    
    def checkout(self, branch_name: str) -> Dict[str, Any]:
        """Checkout a branch."""
        result = self._run_git("checkout", branch_name)
        if result.returncode != 0:
            return {
                "status": "error",
                "message": f"Failed to checkout {branch_name}: {result.stderr}"
            }
        
        return {"status": "success", "branch_name": branch_name}
    
    def execute_split(
        self,
        plan: Dict[str, Any],
        source_path: str,
        target_repo_path: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Execute a split plan by creating branches and copying files.
        
        Args:
            plan: Split plan from SplitPlanner
            source_path: Path to source files
            target_repo_path: Path to target git repository
            dry_run: If True, don't actually make changes
            
        Returns:
            Execution result with created branches
        """
        self.repo_path = Path(target_repo_path).absolute()
        source = Path(source_path).absolute()
        
        if not self.is_git_repo():
            return {
                "status": "error",
                "message": f"Target path is not a git repository: {target_repo_path}"
            }
        
        results = []
        base_branch = plan.get("base_branch", "main")
        
        # First, ensure base branch exists and we're on it
        if not dry_run:
            checkout_result = self.checkout(base_branch)
            if checkout_result.get("status") == "error":
                # Try to create it from main/master
                for fallback in ["main", "master"]:
                    result = self.create_branch(base_branch, fallback)
                    if result.get("status") == "success":
                        break
        
        # Process each PR in the plan
        for pr in plan.get("prs", []):
            branch_name = pr.get("branch_name", "")
            files = pr.get("files", [])
            description = pr.get("description", "")
            
            if dry_run:
                results.append(BranchResult(
                    branch_name=branch_name,
                    status="dry_run",
                    files_added=len(files)
                ))
                continue
            
            # Create branch from base
            branch_result = self.create_branch(branch_name, base_branch)
            if branch_result.get("status") == "error":
                results.append(BranchResult(
                    branch_name=branch_name,
                    status="error",
                    files_added=0,
                    error=branch_result.get("message")
                ))
                continue
            
            # Copy files from source to target
            copied_files = []
            for file_path in files:
                src_file = source / file_path
                dst_file = self.repo_path / file_path
                
                if src_file.exists():
                    # Create parent directories
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file
                    shutil.copy2(src_file, dst_file)
                    copied_files.append(file_path)
            
            if not copied_files:
                results.append(BranchResult(
                    branch_name=branch_name,
                    status="warning",
                    files_added=0,
                    error="No files copied"
                ))
                continue
            
            # Add and commit
            self.add_files(copied_files)
            commit_result = self.commit(f"feat: {description}")
            
            # Push
            push_result = self.push(branch_name)
            
            results.append(BranchResult(
                branch_name=branch_name,
                status="success" if push_result.get("status") == "success" else "partial",
                files_added=len(copied_files),
                commit_hash=commit_result.get("commit_hash"),
                error=push_result.get("message") if push_result.get("status") != "success" else None
            ))
            
            # Go back to base branch for next iteration
            self.checkout(base_branch)
        
        return {
            "status": "success",
            "dry_run": dry_run,
            "branches": [r.to_dict() for r in results],
            "summary": {
                "total_branches": len(results),
                "successful": len([r for r in results if r.status == "success"]),
                "failed": len([r for r in results if r.status == "error"]),
            },
            "executed_at": datetime.now().isoformat()
        }
