"""
Split Plan Generator
Generates intelligent split plans for dividing code into multiple PRs.
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

from .analyzer import CodeAnalyzer, FileInfo, ModuleInfo

logger = logging.getLogger(__name__)


class SplitStrategy(Enum):
    """Strategy for splitting code."""
    BY_MODULE = "by_module"      # Split by top-level modules/directories
    BY_FILE = "by_file"          # Split by individual files
    BY_TYPE = "by_type"          # Split by file type (code, config, docs)
    BY_DEPENDENCY = "by_dependency"  # Split based on dependency order
    BALANCED = "balanced"        # Balance files across PRs by size


@dataclass
class PRDefinition:
    """Definition of a single PR in the split plan."""
    index: int
    name: str
    branch_name: str
    files: List[str]
    description: str
    estimated_lines: int = 0
    depends_on: List[int] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "branch_name": self.branch_name,
            "files": self.files,
            "file_count": len(self.files),
            "description": self.description,
            "estimated_lines": self.estimated_lines,
            "depends_on": self.depends_on
        }


@dataclass
class SplitPlan:
    """Complete split plan for a codebase."""
    source_path: str
    target_pr_count: int
    strategy: SplitStrategy
    base_branch: str
    branch_prefix: str
    prs: List[PRDefinition] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_path": self.source_path,
            "target_pr_count": self.target_pr_count,
            "strategy": self.strategy.value,
            "base_branch": self.base_branch,
            "branch_prefix": self.branch_prefix,
            "prs": [pr.to_dict() for pr in self.prs],
            "summary": {
                "actual_pr_count": len(self.prs),
                "total_files": self.total_files,
                "total_lines": self.total_lines,
                "avg_files_per_pr": self.total_files / len(self.prs) if self.prs else 0,
                "avg_lines_per_pr": self.total_lines / len(self.prs) if self.prs else 0
            },
            "created_at": datetime.now().isoformat()
        }


class SplitPlanner:
    """Generates split plans for code."""
    
    def __init__(self):
        self.analyzer = CodeAnalyzer()
    
    def generate_plan(
        self,
        source_path: str,
        target_pr_count: int = 8,
        strategy: str = "by_module",
        base_branch: str = "main",
        branch_prefix: str = "user/feature"
    ) -> Dict[str, Any]:
        """
        Generate a split plan for the source code.
        
        Args:
            source_path: Path to source directory
            target_pr_count: Target number of PRs
            strategy: Split strategy (by_module, by_file, by_type, balanced)
            base_branch: Base branch name
            branch_prefix: Prefix for generated branch names
            
        Returns:
            Split plan with PR definitions
        """
        # First, analyze the code structure
        analysis = self.analyzer.analyze(source_path)
        
        if analysis.get("status") == "error":
            return analysis
        
        # Parse strategy
        try:
            split_strategy = SplitStrategy(strategy)
        except ValueError:
            split_strategy = SplitStrategy.BY_MODULE
        
        # Create split plan based on strategy
        plan = SplitPlan(
            source_path=source_path,
            target_pr_count=target_pr_count,
            strategy=split_strategy,
            base_branch=base_branch,
            branch_prefix=branch_prefix,
            total_files=analysis["summary"]["total_files"],
            total_lines=analysis["summary"]["total_lines"]
        )
        
        # Generate PRs based on strategy
        if split_strategy == SplitStrategy.BY_MODULE:
            self._split_by_module(plan, analysis)
        elif split_strategy == SplitStrategy.BY_FILE:
            self._split_by_file(plan, analysis)
        elif split_strategy == SplitStrategy.BY_TYPE:
            self._split_by_type(plan, analysis)
        elif split_strategy == SplitStrategy.BALANCED:
            self._split_balanced(plan, analysis)
        else:
            self._split_by_module(plan, analysis)
        
        return {
            "status": "success",
            "plan": plan.to_dict()
        }
    
    def _split_by_module(self, plan: SplitPlan, analysis: Dict[str, Any]):
        """Split by top-level modules/directories."""
        modules = analysis.get("modules", {})
        files_by_module = {}
        
        # Group files by module
        for file_info in analysis.get("files", []):
            module = file_info.get("module", "root")
            if module not in files_by_module:
                files_by_module[module] = []
            files_by_module[module].append(file_info)
        
        # Sort modules by file count (larger modules first)
        sorted_modules = sorted(
            files_by_module.keys(),
            key=lambda m: len(files_by_module[m]),
            reverse=True
        )
        
        # If we have fewer modules than target PRs, split large modules
        if len(sorted_modules) < plan.target_pr_count:
            # Just create one PR per module
            for idx, module in enumerate(sorted_modules):
                files = files_by_module[module]
                pr = PRDefinition(
                    index=idx,
                    name=f"Add {module} module" if module != "root" else "Add root files",
                    branch_name=f"{plan.branch_prefix}-{module.replace('/', '-')}",
                    files=[f["path"] for f in files],
                    description=f"Add {module} module with {len(files)} files",
                    estimated_lines=sum(f.get("lines", 0) for f in files)
                )
                plan.prs.append(pr)
        else:
            # Combine small modules to reach target count
            self._combine_modules_to_target(plan, files_by_module, sorted_modules)
    
    def _combine_modules_to_target(
        self,
        plan: SplitPlan,
        files_by_module: Dict[str, List[Dict]],
        sorted_modules: List[str]
    ):
        """Combine modules to reach target PR count."""
        target = plan.target_pr_count
        
        # Simple distribution: divide modules evenly
        modules_per_pr = max(1, len(sorted_modules) // target)
        
        idx = 0
        for i in range(0, len(sorted_modules), modules_per_pr):
            batch_modules = sorted_modules[i:i + modules_per_pr]
            
            # Collect all files from these modules
            all_files = []
            for module in batch_modules:
                all_files.extend(files_by_module[module])
            
            if not all_files:
                continue
            
            # Create PR definition
            if len(batch_modules) == 1:
                name = f"Add {batch_modules[0]} module"
                suffix = batch_modules[0].replace('/', '-')
            else:
                name = f"Add modules: {', '.join(batch_modules[:3])}"
                if len(batch_modules) > 3:
                    name += f" (+{len(batch_modules) - 3} more)"
                suffix = f"batch-{idx}"
            
            pr = PRDefinition(
                index=idx,
                name=name,
                branch_name=f"{plan.branch_prefix}-{suffix}",
                files=[f["path"] for f in all_files],
                description=f"Add {len(batch_modules)} module(s): {', '.join(batch_modules)}",
                estimated_lines=sum(f.get("lines", 0) for f in all_files)
            )
            plan.prs.append(pr)
            idx += 1
            
            if idx >= target:
                # Add remaining to last PR
                if i + modules_per_pr < len(sorted_modules):
                    remaining_modules = sorted_modules[i + modules_per_pr:]
                    for module in remaining_modules:
                        pr.files.extend(f["path"] for f in files_by_module[module])
                    pr.description += f" (+ {len(remaining_modules)} more modules)"
                break
    
    def _split_by_file(self, plan: SplitPlan, analysis: Dict[str, Any]):
        """Split by individual files, distributing evenly."""
        files = analysis.get("files", [])
        target = plan.target_pr_count
        
        # Sort files by path for consistent ordering
        sorted_files = sorted(files, key=lambda f: f["path"])
        
        # Distribute files evenly
        files_per_pr = max(1, len(sorted_files) // target)
        
        for idx in range(target):
            start = idx * files_per_pr
            if idx == target - 1:
                # Last PR gets all remaining files
                batch_files = sorted_files[start:]
            else:
                batch_files = sorted_files[start:start + files_per_pr]
            
            if not batch_files:
                break
            
            pr = PRDefinition(
                index=idx,
                name=f"Add files batch {idx + 1}",
                branch_name=f"{plan.branch_prefix}-batch-{idx + 1}",
                files=[f["path"] for f in batch_files],
                description=f"Add {len(batch_files)} files",
                estimated_lines=sum(f.get("lines", 0) for f in batch_files)
            )
            plan.prs.append(pr)
    
    def _split_by_type(self, plan: SplitPlan, analysis: Dict[str, Any]):
        """Split by file type (configs first, then code, then docs)."""
        files = analysis.get("files", [])
        
        # Categorize files
        configs = []
        code_files = []
        docs = []
        others = []
        
        code_exts = set(CodeAnalyzer.CODE_EXTENSIONS.keys())
        config_exts = CodeAnalyzer.CONFIG_EXTENSIONS
        doc_exts = CodeAnalyzer.DOC_EXTENSIONS
        
        for f in files:
            ext = f.get("extension", "")
            if ext in config_exts:
                configs.append(f)
            elif ext in code_exts:
                code_files.append(f)
            elif ext in doc_exts:
                docs.append(f)
            else:
                others.append(f)
        
        # Create PRs for each category
        idx = 0
        
        # 1. Configs and setup (PR 0)
        if configs or others:
            pr = PRDefinition(
                index=idx,
                name="Add project configuration",
                branch_name=f"{plan.branch_prefix}-configs",
                files=[f["path"] for f in configs + others],
                description=f"Add configuration files ({len(configs)} config, {len(others)} other)",
                estimated_lines=sum(f.get("lines", 0) for f in configs + others)
            )
            plan.prs.append(pr)
            idx += 1
        
        # 2. Code files (split into multiple PRs if needed)
        remaining_prs = plan.target_pr_count - idx - (1 if docs else 0)
        if code_files and remaining_prs > 0:
            files_per_pr = max(1, len(code_files) // remaining_prs)
            
            for i in range(remaining_prs):
                start = i * files_per_pr
                if i == remaining_prs - 1:
                    batch = code_files[start:]
                else:
                    batch = code_files[start:start + files_per_pr]
                
                if not batch:
                    break
                
                pr = PRDefinition(
                    index=idx,
                    name=f"Add source code batch {i + 1}",
                    branch_name=f"{plan.branch_prefix}-code-{i + 1}",
                    files=[f["path"] for f in batch],
                    description=f"Add {len(batch)} source files",
                    estimated_lines=sum(f.get("lines", 0) for f in batch),
                    depends_on=[0] if configs else []
                )
                plan.prs.append(pr)
                idx += 1
        
        # 3. Documentation (last PR)
        if docs:
            pr = PRDefinition(
                index=idx,
                name="Add documentation",
                branch_name=f"{plan.branch_prefix}-docs",
                files=[f["path"] for f in docs],
                description=f"Add {len(docs)} documentation files",
                estimated_lines=sum(f.get("lines", 0) for f in docs)
            )
            plan.prs.append(pr)
    
    def _split_balanced(self, plan: SplitPlan, analysis: Dict[str, Any]):
        """Split to balance lines of code across PRs."""
        files = analysis.get("files", [])
        target = plan.target_pr_count
        
        # Sort files by lines (descending) for better distribution
        sorted_files = sorted(files, key=lambda f: f.get("lines", 0), reverse=True)
        
        # Use greedy algorithm to balance
        pr_files: List[List[Dict]] = [[] for _ in range(target)]
        pr_lines: List[int] = [0] * target
        
        for f in sorted_files:
            # Add to the PR with fewest lines
            min_idx = pr_lines.index(min(pr_lines))
            pr_files[min_idx].append(f)
            pr_lines[min_idx] += f.get("lines", 0)
        
        # Create PR definitions
        for idx, (files_list, lines) in enumerate(zip(pr_files, pr_lines)):
            if not files_list:
                continue
            
            pr = PRDefinition(
                index=idx,
                name=f"Add files batch {idx + 1} (~{lines} lines)",
                branch_name=f"{plan.branch_prefix}-batch-{idx + 1}",
                files=[f["path"] for f in files_list],
                description=f"Add {len(files_list)} files (~{lines} lines)",
                estimated_lines=lines
            )
            plan.prs.append(pr)
