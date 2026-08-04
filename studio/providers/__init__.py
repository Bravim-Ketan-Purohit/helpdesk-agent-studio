"""Provider client types — the trust boundary starts here.

The read/write split is the load-bearing design decision. ReadOnlyProvider has
no mutating methods; WriteProvider lives in studio.executor and is never imported
from studio.agent.
"""

from studio.providers.base import ReadOnlyProvider, WriteProvider

__all__ = ["ReadOnlyProvider", "WriteProvider"]
