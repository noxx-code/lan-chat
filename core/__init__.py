"""
core/__init__.py
────────────────
Convenience re-exports so callers can write:

    from core import DiscoveryService, MessagingService, FileTransferService
"""

from .discovery     import DiscoveryService
from .messaging     import MessagingService
from .file_transfer import FileTransferService
from .protocol      import Packet, MsgType
from .encryption    import get_cipher

__all__ = [
    "DiscoveryService",
    "MessagingService",
    "FileTransferService",
    "Packet",
    "MsgType",
    "get_cipher",
]
