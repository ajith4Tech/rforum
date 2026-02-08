from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Question
import uuid

router = APIRouter(prefix="/qna", tags=["qna"])

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
async def submit_question(session_id: str, name: str, question: str, db: AsyncSession = Depends(get_db)):
    question_id = uuid.uuid4()
    new_question = Question(id=question_id, session_id=session_id, name=name, question=question)
    db.add(new_question)
    await db.commit()
    return {"question_id": question_id, "name": name, "question": question}