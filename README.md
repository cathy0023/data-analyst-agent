# data-analyst-agent

A Python SDK for embedding conversational data analysis into your application. Users ask questions in natural language; the agent translates them to SQL, executes them against your database, and returns structured data + conclusions.

> **Status**: Prototype / RFC stage. See [docs/rfcs/](docs/rfcs/README.md) for the design process.

## Architecture (planned)

Three-layer design — see [RFC](docs/rfcs/inbox/2026-06-15-data-analyst-agent.md):

- **Agent layer**: LLM decision loop (Claude / OpenAI tool use)
- **Tool layer**: `list_tables` / `get_schema` / `execute_sql` atomic tools
- **Executor layer**: DB connection pool + read-only safety sandbox

## Quick Start

```bash
pip install -e .
```

```python
from data_analyst_agent import DataAnalyst

agent = DataAnalyst(db_url="postgresql://...")
result = agent.ask("上个月华东区 GMV 环比多少？")
print(result)
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

TBD
