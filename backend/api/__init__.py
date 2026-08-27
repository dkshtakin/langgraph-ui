"""HTTP endpoints for the book-planner service.

Exports ``create_router()`` — a FastAPI ``APIRouter`` mounting:
- ``GET /stream`` — SSE streaming from LangGraph agent
"""

from backend.api.routes import create_router

__all__ = ["create_router"]
