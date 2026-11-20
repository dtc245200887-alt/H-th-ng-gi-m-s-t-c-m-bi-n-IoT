from typing import Any

from fastapi import WebSocket

from app.models import Reading, Sensor


class MonitorWorker:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        disconnected: set[WebSocket] = set()
        for connection in self.connections:
            try:
                await connection.send_json(payload)
            except Exception:
                disconnected.add(connection)
        self.connections -= disconnected

    def evaluate(self, sensor: Sensor, reading: Reading) -> dict[str, Any] | None:
        if sensor.min_value is not None and reading.value < sensor.min_value:
            return {
                "level": "warning",
                "message": f"{sensor.name} dropped below {sensor.min_value} {sensor.unit}",
            }
        if sensor.max_value is not None and reading.value > sensor.max_value:
            return {
                "level": "warning",
                "message": f"{sensor.name} exceeded {sensor.max_value} {sensor.unit}",
            }
        return None

    async def close(self) -> None:
        for connection in list(self.connections):
            await connection.close()
        self.connections.clear()
