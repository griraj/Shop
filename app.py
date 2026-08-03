

from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import core

app = FastAPI(title="Ledger — Inventory + AI Clerk")


# ---------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------

class NewItem(BaseModel):
    name: str
    price: float
    stock: int
    category_id: int


class UpdateItemPayload(BaseModel):
    price: Optional[float] = None
    stock: Optional[int] = None
    category_id: Optional[int] = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------
# Inventory endpoints
# ---------------------------------------------------------------------

@app.get("/api/items")
def get_items():
    try:
        return core.list_items()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/categories")
def get_categories():
    try:
        return core.list_categories()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audit")
def get_audit():
    try:
        return core.list_audit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/items")
def create_item(item: NewItem):
    result = core.add_item(item.name, item.price, item.stock, item.category_id)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.put("/api/items/{item_id}")
def edit_item(item_id: int, payload: UpdateItemPayload):
    result = core.update_item(
        item_id,
        price=payload.price,
        stock=payload.stock,
        category_id=payload.category_id,
    )
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.delete("/api/items/{item_id}")
def remove_item(item_id: int):
    result = core.delete_item(item_id)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ---------------------------------------------------------------------
# AI agent endpoint
# ---------------------------------------------------------------------

@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        return core.run_agent(req.message, history=req.history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
