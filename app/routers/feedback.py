from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Feedback
import uuid

router = APIRouter(prefix="/feedback", tags=["feedback"])

active_connections = {}

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    if session_id not in active_connections:
        active_connections[session_id] = []
    active_connections[session_id].append(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            for connection in active_connections[session_id]:
                await connection.send_json(data)
    except WebSocketDisconnect:
        active_connections[session_id].remove(websocket)

@router.post("/")
async def submit_feedback(session_id: str, name: str, feedback: str, db: AsyncSession = Depends(get_db)):
    feedback_id = uuid.uuid4()
    new_feedback = Feedback(id=feedback_id, session_id=session_id, name=name, feedback=feedback)
    db.add(new_feedback)
    await db.commit()
    return {"feedback_id": feedback_id, "name": name, "feedback": feedback}