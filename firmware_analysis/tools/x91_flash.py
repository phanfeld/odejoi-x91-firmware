#!/usr/bin/env python3
"""Moved: the flash procedure lives in x91_dump/x91_flash.py, next to the files it needs. This runs that script."""
import os
import runpy
import sys

LIVE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "x91_dump", "x91_flash.py"))
sys.argv[0] = LIVE
runpy.run_path(LIVE, run_name="__main__")
