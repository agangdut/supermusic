from __future__ import annotations

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set

from ..utils.storage import job_store

router = APIRouter()

# Store active WebSocket connections
active_connections: Set[WebSocket] = set()


async def broadcast_job_update(job_id: str, job_data: dict) -> None:
    """Broadcast job update to all connected clients."""
    message = {
        "type": "job_update",
        "job_id": job_id,
        "data": job_data
    }
    disconnected = set()
    for connection in active_connections:
        try:
            await connection.send_json(message)
        except Exception:
            disconnected.add(connection)
    
    # Remove disconnected connections
    active_connections.difference_update(disconnected)


@router.websocket("/ws/jobs")
async def websocket_jobs(websocket: WebSocket):
    """WebSocket endpoint for real-time job updates."""
    await websocket.accept()
    active_connections.add(websocket)
    
    try:
        # Send initial job list
        jobs = {str(job_id): {
            "id": str(job_id),
            "job_type": job.job_type.value if hasattr(job, "job_type") else None,
            "status": job.status.value if hasattr(job, "status") else None,
            "progress": getattr(job, "progress", None),
            "message": getattr(job, "message", None),
        } for job_id, job in job_store.items()}
        
        await websocket.send_json({
            "type": "initial_jobs",
            "jobs": jobs
        })
        
        # Keep connection alive and handle messages
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                if message.get("type") == "subscribe":
                    job_id = message.get("job_id")
                    if job_id and job_id in job_store:
                        job = job_store[job_id]
                        await websocket.send_json({
                            "type": "job_update",
                            "job_id": job_id,
                            "data": {
                                "id": str(job_id),
                                "job_type": job.job_type.value if hasattr(job, "job_type") else None,
                                "status": job.status.value if hasattr(job, "status") else None,
                                "progress": getattr(job, "progress", None),
                                "message": getattr(job, "message", None),
                            }
                        })
            except json.JSONDecodeError:
                pass
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
    except WebSocketDisconnect:
        active_connections.discard(websocket)

