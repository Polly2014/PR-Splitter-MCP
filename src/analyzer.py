"""
Code Structure Analyzer
Analyzes code structure, detects modules, and understands file dependencies.
"""

import os
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """Information about a single file."""
    path: str
    name: str
    extension: str
    size: int
    lines: int
    module: str
    imports: List[str] = field(default_factory=list)
    modified: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "extension": self.extension,
            "size": self.size,
            "lines": self.lines,
            "module": self.module,
            "imports": self.imports,
            "modified": self.modified
        }


@dataclass
class ModuleInfo:
    """Information about a module/directory."""
    name: str
    path: str
    files: List[FileInfo] = field(default_factory=list)
    submodules: List[str] = field(default_factory=list)
    total_lines: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "file_count": len(self.files),
            "files": [f.to_dict() for f in self.files],
            "submodules": self.submodules,
            "total_lines": self.total_lines
        }


class CodeAnalyzer:
    """Analyzes code structure and dependencies."""
    
    # Common code file extensions
    CODE_EXTENSIONS = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.jsx': 'javascript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.cs': 'csharp',
        '.go': 'go',
        '.rs': 'rust',
        '.cpp': 'cpp',
        '.c': 'c',
        '.h': 'c',
        '.hpp': 'cpp',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.scala': 'scala',
    }
    
    # Config file extensions
    CONFIG_EXTENSIONS = {
        '.yaml', '.yml', '.json', '.toml', '.ini', '.cfg', '.conf',
        '.xml', '.properties', '.env'
    }
    
    # Documentation extensions
    DOC_EXTENSIONS = {
        '.md', '.rst', '.txt', '.adoc'
    }
    
    # Patterns to ignore
    IGNORE_PATTERNS = {
        '__pycache__', '.git', '.svn', 'node_modules', 'venv', '.venv',
        'env', '.env', 'dist', 'build', '.idea', '.vscode', '*.egg-info',
        '.pytest_cache', '.mypy_cache', '__snapshots__'
    }
    
    def __init__(self):
        self.files: List[FileInfo] = []
        self.modules: Dict[str, ModuleInfo] = {}
        self.dependencies: Dict[str, Set[str]] = {}
    
    def analyze(
        self,
        source_path: str,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyze the code structure of a directory.
        
        Args:
            source_path: Path to the source directory
            include_patterns: File patterns to include (glob)
            exclude_patterns: File patterns to exclude (glob)
            
        Returns:
            Analysis result with modules, files, and dependencies
        """
        self.files = []
        self.modules = {}
        self.dependencies = {}
        
        source = Path(source_path)
        if not source.exists():
            return {
                "status": "error",
                "message": f"Source path does not exist: {source_path}"
            }
        
        if not source.is_dir():
            return {
                "status": "error",
                "message": f"Source path is not a directory: {source_path}"
            }
        
        # Scan all files
        self._scan_directory(source, source, include_patterns, exclude_patterns)
        
        # Analyze dependencies
        self._analyze_dependencies()
        
        # Build module hierarchy
        self._build_module_hierarchy()
        
        return {
            "status": "success",
            "source_path": str(source.absolute()),
            "summary": {
                "total_files": len(self.files),
                "total_modules": len(self.modules),
                "total_lines": sum(f.lines for f in self.files),
                "by_extension": self._count_by_extension(),
                "by_type": self._count_by_type()
            },
            "modules": {name: mod.to_dict() for name, mod in self.modules.items()},
            "files": [f.to_dict() for f in self.files],
            "dependencies": {k: list(v) for k, v in self.dependencies.items()},
            "analyzed_at": datetime.now().isoformat()
        }
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored."""
        for pattern in self.IGNORE_PATTERNS:
            if pattern in str(path):
                return True
        return False
    
    def _scan_directory(
        self,
        directory: Path,
        root: Path,
        include_patterns: Optional[List[str]],
        exclude_patterns: Optional[List[str]]
    ):
        """Recursively scan a directory for code files."""
        try:
            for item in directory.iterdir():
                if self._should_ignore(item):
                    continue
                
                if item.is_dir():
                    self._scan_directory(item, root, include_patterns, exclude_patterns)
                elif item.is_file():
                    # Check patterns
                    if include_patterns:
                        if not any(item.match(p) for p in include_patterns):
                            continue
                    if exclude_patterns:
                        if any(item.match(p) for p in exclude_patterns):
                            continue
                    
                    # Process file
                    file_info = self._analyze_file(item, root)
                    if file_info:
                        self.files.append(file_info)
        except PermissionError:
            logger.warning(f"Permission denied: {directory}")
    
    def _analyze_file(self, file_path: Path, root: Path) -> Optional[FileInfo]:
        """Analyze a single file."""
        ext = file_path.suffix.lower()
        
        # Only process known file types
        all_extensions = (
            set(self.CODE_EXTENSIONS.keys()) | 
            self.CONFIG_EXTENSIONS | 
            self.DOC_EXTENSIONS
        )
        if ext not in all_extensions:
            return None
        
        try:
            # Get basic info
            stat = file_path.stat()
            rel_path = file_path.relative_to(root)
            
            # Determine module (parent directory)
            if len(rel_path.parts) > 1:
                module = rel_path.parts[0]
            else:
                module = "root"
            
            # Count lines and extract imports
            lines = 0
            imports = []
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    lines = len(content.splitlines())
                    
                    # Extract imports based on language
                    if ext == '.py':
                        imports = self._extract_python_imports(content)
                    elif ext in ['.js', '.ts', '.jsx', '.tsx']:
                        imports = self._extract_js_imports(content)
            except Exception as e:
                logger.debug(f"Error reading file {file_path}: {e}")
            
            return FileInfo(
                path=str(rel_path),
                name=file_path.name,
                extension=ext,
                size=stat.st_size,
                lines=lines,
                module=module,
                imports=imports,
                modified=datetime.fromtimestamp(stat.st_mtime).isoformat()
            )
        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {e}")
            return None
    
    def _extract_python_imports(self, content: str) -> List[str]:
        """Extract import statements from Python code."""
        imports = []
        
        # Match 'import xxx' and 'from xxx import yyy'
        import_pattern = r'^(?:from\s+(\S+)\s+import|import\s+(\S+))'
        
        for line in content.splitlines():
            line = line.strip()
            match = re.match(import_pattern, line)
            if match:
                module = match.group(1) or match.group(2)
                if module:
                    # Get the top-level module
                    top_module = module.split('.')[0]
                    if top_module not in imports:
                        imports.append(top_module)
        
        return imports
    
    def _extract_js_imports(self, content: str) -> List[str]:
        """Extract import statements from JavaScript/TypeScript code."""
        imports = []
        
        # Match various import patterns
        patterns = [
            r"import\s+.*?\s+from\s+['\"](.+?)['\"]",
            r"require\s*\(\s*['\"](.+?)['\"]",
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                module = match.group(1)
                if module and not module.startswith('.'):
                    # Get the package name (first part)
                    pkg = module.split('/')[0]
                    if pkg not in imports:
                        imports.append(pkg)
        
        return imports
    
    def _analyze_dependencies(self):
        """Build dependency graph between files."""
        # Group files by module
        module_files = {}
        for f in self.files:
            if f.module not in module_files:
                module_files[f.module] = []
            module_files[f.module].append(f)
        
        # Build dependencies based on imports
        for f in self.files:
            deps = set()
            for imp in f.imports:
                # Check if import matches any module
                if imp in module_files:
                    deps.add(imp)
            
            if deps:
                self.dependencies[f.path] = deps
    
    def _build_module_hierarchy(self):
        """Build module hierarchy from files."""
        for f in self.files:
            module_name = f.module
            
            if module_name not in self.modules:
                # Determine module path
                if module_name == "root":
                    module_path = "."
                else:
                    module_path = module_name
                
                self.modules[module_name] = ModuleInfo(
                    name=module_name,
                    path=module_path
                )
            
            self.modules[module_name].files.append(f)
            self.modules[module_name].total_lines += f.lines
    
    def _count_by_extension(self) -> Dict[str, int]:
        """Count files by extension."""
        counts = {}
        for f in self.files:
            ext = f.extension
            counts[ext] = counts.get(ext, 0) + 1
        return counts
    
    def _count_by_type(self) -> Dict[str, int]:
        """Count files by type category."""
        counts = {"code": 0, "config": 0, "docs": 0, "other": 0}
        
        for f in self.files:
            ext = f.extension
            if ext in self.CODE_EXTENSIONS:
                counts["code"] += 1
            elif ext in self.CONFIG_EXTENSIONS:
                counts["config"] += 1
            elif ext in self.DOC_EXTENSIONS:
                counts["docs"] += 1
            else:
                counts["other"] += 1
        
        return counts
