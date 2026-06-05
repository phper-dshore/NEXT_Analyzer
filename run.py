"""Launch script for the S4P Network Analyzer application."""

import sys
import os

# Ensure the project root is in the path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from main import main

if __name__ == "__main__":
    main()
