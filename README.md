# firesim-ai

Agentic AI layer on top of [FireMapSim](https://github.com/example/firemapsim) that lets non-technical users (e.g. farmers) run wildfire simulations through a conversational chat interface.

## Overview

- Natural language → simulation parameters (including coordinate translation)
- Runs FireMapSim and returns human-readable results
- REST API via FastAPI for chat clients

## Tech stack

Python 3.11+, LangChain, LangGraph, FastAPI, Pydantic, OpenAI or Anthropic LLMs.

## Quick start

1. Copy `.env.example` to `.env` and fill in values.
2. Create a virtual environment and install dependencies: `pip install -r requirements.txt`
3. Run the API: `uvicorn main:app --reload`

## Project layout

See repository tree under `app/` for agent, tools, FireMapSim client, and API routes.

## Status

Scaffolding only — implementation in progress.
