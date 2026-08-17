#!/usr/bin/env python3
"""Entry point for `python calyre_entry.py ...` and for the PyInstaller build."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calyre.cli import main

if __name__ == "__main__":
    main()
