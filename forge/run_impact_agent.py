"""
Forge Impact Analysis CLI.

Entry point for running the Impact Analysis Agent.
Uses the code graph database to answer "what breaks if I change X?"

Usage:
    # Set up environment
    cd forge
    pip install google-adk google-genai python-dotenv kuzu
    
    # Create .env with your API key
    echo "GOOGLE_API_KEY=your-key" > .env
    
    # Run interactive mode
    python run_impact_agent.py
    
    # Or with a specific query
    python run_impact_agent.py --query "What breaks if I change validatePayment?"
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Forge Impact Analysis Agent")
    parser.add_argument("--query", "-q", help="Single query to analyze")
    parser.add_argument("--graph", "-g", default="../data/code_graph.kuzu",
                        help="Path to the code graph database")
    args = parser.parse_args()
    
    # Check API key
    if not os.getenv("GOOGLE_API_KEY"):
        print("ERROR: GOOGLE_API_KEY not set")
        print("Create .env file with: GOOGLE_API_KEY=your-key")
        sys.exit(1)
    
    # Resolve graph path
    graph_path = Path(args.graph)
    if not graph_path.is_absolute():
        graph_path = Path(__file__).parent / args.graph
    
    if not graph_path.exists():
        print(f"ERROR: Graph database not found at {graph_path}")
        print("\nTo create the graph, run:")
        print("  cd code_graph")
        print("  python visualize_graph.py")
        sys.exit(1)
    
    # Import here after path setup
    from modules.agents.impact import ImpactAgent
    
    # Import the graph store - need to set up code_graph as a proper package import
    code_graph_path = Path(__file__).parent / "code_graph"
    sys.path.insert(0, str(code_graph_path.parent))
    
    from code_graph.graph.store import KuzuGraphStore
    
    print("=" * 60)
    print("FORGE IMPACT ANALYSIS AGENT")
    print("=" * 60)
    print(f"\nGraph: {graph_path}")
    
    # Open graph store
    store = KuzuGraphStore(graph_path)
    agent = ImpactAgent(store)
    
    print(f"Services: {', '.join(agent.services)}")
    print(f"Symbols: {agent.symbol_count}")
    
    if args.query:
        # Single query mode
        print("\n" + "-" * 60)
        print(f"Query: {args.query}")
        print("-" * 60 + "\n")
        
        response = asyncio.run(agent.analyze(args.query))
        safe_response = response.replace('\u2192', '->').replace('\u2190', '<-')
        print(safe_response)
    else:
        # Interactive mode
        asyncio.run(agent.run_interactive())
    
    store.close()


if __name__ == "__main__":
    main()
