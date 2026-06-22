"""WebSocket gateway (build step 5).

One socket per client; subscribes to channels (feed:global, sym:DSE:GP, ...). Ingestion/ai_worker
publish to Redis pub/sub; this fans out to subscribed sockets. When the licensed feed lands, the
SAME channels carry real-time ticks — client code unchanged.

STATUS: STUB.
"""

from __future__ import annotations
