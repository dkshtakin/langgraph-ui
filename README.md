# langgraph-ui

![langgraph-ui](img/langgraph-ui.png)

Frontend service for interacting with arbitrary graphs using langgraph agent server.
 - Streaming responses (resoning, text, tool calls)
 - Supports chatting with your graphs via 'messages' key.
 - Persistent chat history, graphs switcher
 - Supports dynamic reloading during graphs stream

## Overview

Application consists of backend and frontend serivces. Backend provides necessary api routes for interacting with graphs (start, resume, list threads and etc), frontend provides web application for launching your graphs, viewing their output in streaming mode and interacting with their state (used for chatting via `messages` key).

## setup
First, install requirements.txt:
```
pip install -r requirements.txt
```
Run backend and frontend service in separate terminals:
```
# backend
cd backend
langgraph dev

# frontend
cd frontend
npm run dev
```

## user graphs

All user graphs should be placed inside `backend/graphs/user/<user_graph_name>`. Backend service will automatically scan this folder on start up and try to compile all user graphs.

On error pop-up window is shown and graphs can be reloaded via `reload` button in the ui.

### chat

`backend/graphs/examples/chat/chat.py`

This is the example of a single graph including single agent with tools for demonstration.

### book_planner

`backend/graphs/examples/book_planner/book_planner.py`
This is the example of a single graph that uses multiple langchain agents with tools, custom middleware, conditional loop-exit and structured output.

![book_planner](backend/graphs/examples/book_planner/book_planner.mermaid.png)
