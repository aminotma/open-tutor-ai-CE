"""
OpenTutorAI patches package for OpenWebUI integration and environment configuration.

This module serves dual purposes:
1. Bootstrap: Configures environment variables (DATA_DIR) and custom print behavior
2. Package: Provides access to OpenWebUI patches submodules
"""

import os
import builtins
from pathlib import Path

# ============================================================================
# BOOTSTRAP CONFIGURATION (from patches.py)
# ============================================================================

# Set DATA_DIR to backend/data by default
backend_dir = Path(__file__).parent.parent.parent
data_dir = backend_dir / "data"
data_dir.mkdir(exist_ok=True)

if "DATA_DIR" not in os.environ:
    os.environ["DATA_DIR"] = str(data_dir.absolute())
    print(f"Setting default DATA_DIR to: {os.environ['DATA_DIR']}")

original_print = builtins.print

# Signature line to detect the WebUI banner (use a unique line from that banner)
WEBUI_SIGNATURE_LINE = """
 ██████╗ ██████╗ ███████╗███╗   ██╗    ██╗    ██╗███████╗██████╗ ██╗   ██╗██╗
██╔═══██╗██╔══██╗██╔════╝████╗  ██║    ██║    ██║██╔════╝██╔══██╗██║   ██║██║
██║   ██║██████╔╝█████╗  ██╔██╗ ██║    ██║ █╗ ██║█████╗  ██████╔╝██║   ██║██║
██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║    ██║███╗██║██╔══╝  ██╔══██╗██║   ██║██║
╚██████╔╝██║     ███████╗██║ ╚████║    ╚███╔███╔╝███████╗██████╔╝╚██████╔╝██║
 ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝     ╚══╝╚══╝ ╚══════╝╚═════╝  ╚═════╝ ╚═╝
"""


def custom_print(*args, **kwargs):
    output = " ".join(str(arg) for arg in args)

    # Detect the WebUI banner using a unique line
    if WEBUI_SIGNATURE_LINE in output:
        if os.environ.get("SUPPRESS_WEBUI_BANNER") == "true":
            return  # Suppress the banner
    return original_print(*args, **kwargs)


builtins.print = custom_print

__all__ = ['custom_print', 'WEBUI_SIGNATURE_LINE']
