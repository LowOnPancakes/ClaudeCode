"""
Entry point cPanel's "Setup Python App" (Phusion Passenger) looks for.
Not used when running locally with `python app.py` - only needed on cPanel.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app as application  # noqa: E402,F401
