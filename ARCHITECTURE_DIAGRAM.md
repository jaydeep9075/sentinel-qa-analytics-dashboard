# Sentinel QA Architecture Diagram

```mermaid
flowchart TD
    A[Data Sources\nAllure | Files | DB | APIs] --> B[Universal Ingester]
    B --> C[LanceDB\nStructured + Documents + Memory]
    C --> D[DuckDB Query Layer]

    E[Frontend Next.js] --> F[FastAPI Service]
    F --> D
    F --> C
    F --> G[LLM Providers\nGemini/OpenAI/Anthropic/Ollama]

    F --> H[Chat Handler]
    F --> I[Chart Handler]
    H --> J[Learning Signals]
    H --> K[Knowledge Graph Edges]
    I --> J

    J --> H
    K --> H

    F --> L[Auth JWT + Workspace Scope]
    L --> M[Admin Cross-User Controls]

    N[Ingestion Summary + Parser Insights] --> E
```
