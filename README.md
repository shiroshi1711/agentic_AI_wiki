# LoreWeaver - Agentic knowledge management system for creative writing

A local-first, entity-aware Retrieval-Augmented Generation (RAG) assistant designed to eliminate context drift and hallucinations in long-form creative writing using an Obsidian vault as a structured knowledge base.

## Problem

Standard RAG pipelines rely purely on semantic similarity (chunking text into small pieces), which often breaks narrative continuity. When writing complex stories, an LLM might retrieve a character's dialogue style while missing crucial worldbuilding rules or hidden relationships stored in separate notes.

## Core Architecture & Features


### 1. Hybrid GraphRAG & Retrieval Engine
* **Markdown-Aware Parsing:** Extracts structured metadata, character attributes, and lore relationships from Obsidian notes.
* **Dual-Indexing:** Combines dense vector embeddings (semantic search) with a knowledge graph (entity & event traversal) to preserve narrative continuity.
* **Agentic Query Rewriting:** Decomposes and refines user prompts prior to retrieval for higher context accuracy.

### 2. Autonomous Write/Edit Agent with HITL Approval
* **Telegram Bot Interface:** Query wiki lore, propose new entries, or request edits to existing Markdown notes directly from mobile via Telegram.
* **Context-Aware Drafting:** Retrieves existing canon via Hybrid GraphRAG before drafting updates to prevent lore contradictions.
* **Human-in-the-Loop (HITL) Guardrail:** Changes are staged as previews/diffs and sent back to the user for explicit approval (`Approve` / `Reject`) before writing directly to the Obsidian vault.

### 3. 100% Local AI Execution
* Powered locally via **Ollama** (LLM & embedding models), ensuring complete privacy over creative writing and personal knowledge bases.

## Workflow Overview
```text
[Telegram Message] 
       │
       ▼
[Query Rewriter & Hybrid GraphRAG] ──► Retrieves existing Obsidian canon
       │
       ▼
[Agent Drafts New Note / Edit Diff]
       │
       ▼
[Telegram Approval Prompt] ──(Rejected)──► Discard / Revise
       │
   (Approved)
       │
       ▼
[Commit & Re-index to Obsidian Vault]
```

## Tech Stack
- Python 3.14
- Local LLM & Embeddings: Ollama(Qwen3, Nomic-embed-text)
- Retrieval: Hybrid search (Vector store + Knowledge graph)
- Interface & HITL: Telegram Bot API

## Getting Started


## Author

Novia F Malia