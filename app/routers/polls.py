from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Poll, PollOption
import uuid

router = APIRouter(prefix="/polls", tags=["polls"])

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
async def create_poll(session_id: str, question: str, options: list[str], db: AsyncSession = Depends(get_db)):
    poll_id = uuid.uuid4()
    poll = Poll(id=poll_id, session_id=session_id, question=question)
    db.add(poll)
    for option in options:
        poll_option = PollOption(id=uuid.uuid4(), poll_id=poll_id, option_text=option)
        db.add(poll_option)
    await db.commit()
    return {"poll_id": poll_id, "question": question, "options": options}