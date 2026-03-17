"""
OpenBalance Agent Tools — open-source toolkit for AI agents.

pip install openbalance-tools
"""
__version__ = "0.1.0"

from .client import OpenBalanceClient
from .middleware import openbalance_fetch
from .mcp_server import serve as serve_mcp
