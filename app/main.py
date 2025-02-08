import asyncio
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.manager.task_manager import TaskManager


load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)

app = FastAPI()


@app.websocket("/ws/chat/{agent_id}")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    manager = TaskManager({}, websocket=websocket)
    manager_task = None
    try:
        manager_task = asyncio.create_task(manager.run())
        await manager_task
    except WebSocketDisconnect:
        manager.cleanup()
        manager_task.cancel()
        logger.info("WebSocket connection closed")