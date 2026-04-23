# Cortex Deployment Guide

This guide covers deploying cortex-recall across different runtime environments.

---

## Default: Filesystem + Local ChromaDB

Zero configuration required. This is the v0.5.0 behavior and the default for all installs.

```bash
pip install cortex-recall
```

Storage locations:
- STM events: `~/.cortex/stm/72h.jsonl`
- Vector store: `~/.cortex/palace/` (ChromaDB)
- KV store: `~/.cortex/kv/`
- Config: `~/.cortex/config.yaml`

This works on any long-lived host (Linux, macOS, EC2, ECS, Kubernetes).

---

## Serverless: Lambda, Cloud Functions, Cloud Run

Serverless runtimes have ephemeral filesystems and no persistent local storage. v0.6.0 introduces in-memory backends that work on any serverless runtime.

### What works on Lambda in v0.6.0

- `cortex.stm.STM` with any backend (log events, fetch, prune)
- `cortex.dream.Dream` with any backends (nightly maintenance)
- Custom backends registered at handler startup

### Lambda handler example

```python
from cortex.stm import STM
from cortex.backends.memory import MemorySTMBackend

# In-memory STM -- events persist only within the container's lifetime
stm = STM(backend=MemorySTMBackend())

def handler(event, context):
    stm.log({
        "epoch": int(__import__("time").time()),
        "project": "my-lambda",
        "query_head": event.get("query", ""),
    })
    return {"statusCode": 200}
```

### Lambda config via environment variable

```bash
# In Lambda function configuration
CORTEX_CONFIG_PATH=/opt/cortex-config.yaml
```

Config file (mounted via Lambda Layer at `/opt/cortex-config.yaml`):

```yaml
backends:
  stm:
    type: memory
  vector:
    type: memory
  kv:
    type: memory
```

The `CORTEX_CONFIG_PATH` env var is the Lambda-preferred config injection mechanism. It avoids requiring `~/.cortex/` to exist in an ephemeral filesystem.

### Lambda nightly maintenance with memory backends

```python
from cortex.dream import Dream
from cortex.backends.memory import MemoryVectorBackend, MemorySTMBackend, MemoryKVBackend

dream = Dream(
    vector_backend=MemoryVectorBackend(),
    stm_backend=MemorySTMBackend(),
    kv_backend=MemoryKVBackend(),
)
result = dream.run()
```

### Remote deployments (Kubernetes, ECS, long-lived VMs)

For long-lived hosts, local ChromaDB on a network-attached volume works fine:

```yaml
# ~/.cortex/config.yaml on an ECS task with EFS mount
backends:
  stm:
    type: filesystem
    path: /efs/cortex/stm/72h.jsonl
  vector:
    type: chromadb_local
    path: /efs/cortex/palace
  kv:
    type: filesystem
    path: /efs/cortex/kv
```

---

## Writing a Custom Backend

Subclass one of the three abstract base classes from `cortex.backends.base`:

```python
from cortex.backends.base import STMBackend
from cortex.backends import register_backend
from typing import Dict, List, Optional

class DynamoDBSTMBackend(STMBackend):
    def __init__(self, table_name: str, region: str = "us-east-1"):
        import boto3
        self._table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    def append(self, event: dict) -> bool:
        self._table.put_item(Item=event)
        return True

    def fetch(self, window_hours: int = 72, filters: Optional[Dict] = None) -> List[Dict]:
        # ... implement your query logic
        pass

    def prune(self, older_than_hours: int = 72) -> Dict:
        # ... implement your delete-old-items logic
        return {"kept": 0, "dropped": 0}

# Register at app startup
register_backend("stm", "dynamodb", lambda cfg: DynamoDBSTMBackend(
    table_name=cfg.get("table_name", "cortex-stm"),
    region=cfg.get("region", "us-east-1"),
))
```

Then in config.yaml:

```yaml
backends:
  stm:
    type: dynamodb
    table_name: my-cortex-stm-table
    region: us-west-2
```

### Registering via Python entry_points

For installable backend packages, register via `pyproject.toml`:

```toml
[project.entry-points."cortex.backends"]
"stm.dynamodb" = "cortex_backend_dynamodb:DynamoDBSTMFactory"
"vector.opensearch" = "cortex_backend_opensearch:OpenSearchVectorFactory"
```

Factories are discovered automatically at import time.

---

## Known Limitations in v0.6.0

**v0.6.0 abstracts storage for STM and Dream maintenance only.** The following code paths still hit a local ChromaDB directly and are NOT yet compatible with serverless/remote deployments:

- **L3 semantic search** (`cortex.searcher`, `cortex.layers.Layer2`, `cortex.layers.Layer3`) -- calling `cortex_search` from a Lambda will fail unless the Lambda also has a local ChromaDB path mounted. Use a persistent host (ECS, VM) for L3 search in v0.6.0.
- **MCP server** (`cortex.mcp_server`) -- the MCP server opens a ChromaDB client at startup and cannot yet run on Lambda. Host the MCP server on a long-lived process (EC2, container) and have Lambda handlers call cortex APIs directly.
- **Palace writes** (`cortex.palace`, `cortex.miner`) -- ingestion still writes to local ChromaDB.

**What works on Lambda in v0.6.0:**

- `cortex.stm.STM` with any backend (log events, fetch, prune)
- `cortex.dream.Dream` with any backends (nightly maintenance)
- Custom backends registered at handler startup

**Roadmap:** full L3 + MCP abstraction is planned for v0.7.0.

---

## Back-compat Guarantees

All v0.5.0 public APIs work identically in v0.6.0:

```python
# These all work unchanged:
from cortex.stm import STM
stm = STM()                        # filesystem default
stm = STM(path="/custom/path")     # custom path
stm.log(event)
stm.fetch()
stm.rollup()
stm.prune()

from cortex.dream import Dream
Dream().run()                      # filesystem defaults for all steps
```

No migration required for existing installs.
