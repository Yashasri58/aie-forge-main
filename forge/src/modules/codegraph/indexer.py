"""
Multi-Repo CodeGraph Indexer
============================

Uses codegraph-tools to extract symbols and call relationships from multiple
microservice repositories. Produces extraction.json files that can be loaded
into NetworkX for querying.

Key Features:
- Batch extraction across multiple repos
- Automatic language detection
- Node tagging with repo/service ID
- Combined extraction output

Usage:
    indexer = CodeGraphIndexer('./services')
    extraction = indexer.index_all()
    # extraction contains all nodes/edges from all repos
"""

import json
import logging
from pathlib import Path
from typing import Optional

# Import codegraph-tools
try:
    from codegraph.extract import extract, collect_files
    from codegraph.build import build
    import networkx as nx
    CODEGRAPH_AVAILABLE = True
except ImportError:
    CODEGRAPH_AVAILABLE = False
    extract = None
    collect_files = None
    build = None
    nx = None

logger = logging.getLogger(__name__)


class CodeGraphIndexer:
    """
    Multi-repo code indexer using codegraph-tools.
    
    Extracts symbols (functions, classes, methods) and call relationships
    from all microservice repositories in a directory.
    """
    
    # File extensions to index
    SUPPORTED_EXTENSIONS = {'.js', '.ts', '.jsx', '.tsx', '.py', '.java'}
    
    # Directories to skip
    SKIP_DIRS = {'node_modules', '.git', 'dist', 'build', '__pycache__', '.venv', 'venv', 'codegraph-out'}
    
    def __init__(self, services_path: str | Path, output_dir: Optional[str | Path] = None):
        """
        Args:
            services_path: Root directory containing microservice repos
            output_dir: Where to save extraction JSONs (default: services_path/codegraph-out)
        """
        if not CODEGRAPH_AVAILABLE:
            raise ImportError(
                "codegraph-tools not installed. Run: pip install codegraph-tools"
            )
        
        self.services_path = Path(services_path)
        self.output_dir = Path(output_dir) if output_dir else self.services_path / "codegraph-out"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Discover repos (directories with package.json or src/)
        self._repos = self._discover_repos()
        logger.info(f"Discovered {len(self._repos)} repos in {self.services_path}")
    
    def _discover_repos(self) -> list[Path]:
        """Find all microservice repositories in the services directory."""
        repos = []
        for item in self.services_path.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith('.') or item.name in self.SKIP_DIRS:
                continue
            # Check for markers of a code repo
            if (item / 'package.json').exists() or (item / 'src').exists() or \
               (item / 'setup.py').exists() or (item / 'pom.xml').exists():
                repos.append(item)
        return repos
    
    @property
    def repos(self) -> list[str]:
        """List of discovered repo names."""
        return [r.name for r in self._repos]
    
    def _collect_code_files(self, repo_path: Path) -> list[Path]:
        """Collect code files from a repository, skipping unwanted directories."""
        import os
        code_files = []
        for root, dirs, files in os.walk(repo_path):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS and not d.startswith('.')]
            
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix in self.SUPPORTED_EXTENSIONS:
                    code_files.append(file_path)
        return code_files
    
    def index_repo(self, repo_path: Path) -> dict:
        """
        Extract symbols and calls from a single repository.
        
        Args:
            repo_path: Path to the repository
            
        Returns:
            Extraction dict with nodes and edges
        """
        repo_name = repo_path.name
        logger.info(f"Indexing {repo_name}...")
        
        # Collect files using our own method (more reliable than codegraph's)
        code_files = self._collect_code_files(repo_path)
        
        if not code_files:
            logger.warning(f"No code files found in {repo_name}")
            return {"nodes": [], "edges": [], "repo": repo_name}
        
        logger.info(f"  Found {len(code_files)} code files")
        
        # Extract using codegraph-tools
        extraction = extract(code_files)
        
        # Tag nodes and edges with repo ID
        for node in extraction.get("nodes", []):
            node["repo"] = repo_name
            # Normalize source_file to be relative to repo
            if "source_file" in node:
                try:
                    source_path = Path(node["source_file"])
                    node["source_file"] = str(source_path.relative_to(repo_path))
                except ValueError:
                    pass
        
        for edge in extraction.get("edges", []):
            edge["repo"] = repo_name
        
        extraction["repo"] = repo_name
        
        node_count = len(extraction.get("nodes", []))
        edge_count = len(extraction.get("edges", []))
        logger.info(f"  Extracted {node_count} nodes, {edge_count} edges")
        
        return extraction
    
    def index_all(self, save_individual: bool = True) -> dict:
        """
        Index all repositories and produce combined extraction.
        
        Args:
            save_individual: If True, save per-repo extraction JSONs
            
        Returns:
            Combined extraction dict with all nodes and edges
        """
        all_extractions = []
        
        for repo_path in self._repos:
            try:
                extraction = self.index_repo(repo_path)
                all_extractions.append(extraction)
                
                # Save individual repo extraction
                if save_individual:
                    output_file = self.output_dir / f"{repo_path.name}_extraction.json"
                    self._save_json(extraction, output_file)
                    
            except Exception as e:
                logger.error(f"Failed to index {repo_path.name}: {e}")
                continue
        
        # Merge all extractions
        combined = self._merge_extractions(all_extractions)
        
        # Save combined extraction
        combined_file = self.output_dir / "combined_extraction.json"
        self._save_json(combined, combined_file)
        logger.info(f"Saved combined extraction to {combined_file}")
        
        return combined
    
    def _merge_extractions(self, extractions: list[dict]) -> dict:
        """Merge multiple extractions into one."""
        combined = {
            "nodes": [],
            "edges": [],
            "repos": [],
            "input_tokens": 0,
            "output_tokens": 0,
        }
        
        for ext in extractions:
            combined["nodes"].extend(ext.get("nodes", []))
            combined["edges"].extend(ext.get("edges", []))
            if ext.get("repo"):
                combined["repos"].append(ext["repo"])
            combined["input_tokens"] += ext.get("input_tokens", 0)
            combined["output_tokens"] += ext.get("output_tokens", 0)
        
        logger.info(
            f"Combined: {len(combined['nodes'])} nodes, "
            f"{len(combined['edges'])} edges from {len(combined['repos'])} repos"
        )
        
        return combined
    
    def _save_json(self, data: dict, path: Path) -> None:
        """Save data to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
    
    def load_extraction(self, path: Optional[str | Path] = None) -> dict:
        """
        Load an extraction from JSON file.
        
        Args:
            path: Path to extraction JSON (default: combined_extraction.json)
        """
        if path is None:
            path = self.output_dir / "combined_extraction.json"
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def build_networkx_graph(self, extraction: Optional[dict] = None) -> "nx.DiGraph":
        """
        Build a NetworkX directed graph from extraction data.
        
        Args:
            extraction: Extraction dict (loads combined if None)
            
        Returns:
            NetworkX DiGraph with all nodes and edges
        """
        if extraction is None:
            extraction = self.load_extraction()
        
        return build([extraction], directed=True)


def index_services(services_path: str, output_dir: Optional[str] = None) -> dict:
    """
    Convenience function to index all services.
    
    Args:
        services_path: Path to services directory
        output_dir: Where to save output (optional)
        
    Returns:
        Combined extraction dict
    """
    indexer = CodeGraphIndexer(services_path, output_dir)
    return indexer.index_all()
