#!/usr/bin/env python3
"""Start Dzinde: python3 run.py [file.rmtree] [--port 8642] [--no-browser] [--desktop]"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dzinde import server  # noqa: E402

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Dzinde genealogy (RootsMagic-compatible)')
    ap.add_argument('file', nargs='?', help='.rmtree file to open')
    ap.add_argument('--port', type=int, default=8642)
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--desktop', action='store_true', help='native window (needs: pip install pywebview)')
    a = ap.parse_args()
    if a.desktop:
        from dzinde import desktop
        desktop.main([a.file] if a.file else [])
    else:
        server.serve(a.port, a.file, not a.no_browser)
