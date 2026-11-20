from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import create_database, get_session
from app.models import Sensor, Reading
from app.schemas import (
    ReadingCreate,
    ReadingResponse,
    SensorCreate,
    SensorResponse,
    SensorUpdate,
)
from app.services.alerting import MonitorWorker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await create_database()
    app.state.worker = MonitorWorker()
    yield
    await app.state.worker.close()


app = FastAPI(
    title="IoT Sensor Monitoring",
    description="Distributed IoT sensor monitoring API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_path), name="static")


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard() -> str:
    return (static_path / "index.html").read_text(encoding="utf-8")


@app.post("/sensors", response_model=SensorResponse, status_code=status.HTTP_201_CREATED)
async def register_sensor(
    payload: SensorCreate,
    session: AsyncSession = Depends(get_session),
) -> Sensor:
    existing = await session.scalar(select(Sensor).where(Sensor.code == payload.code))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sensor code already exists")

    sensor = Sensor(**payload.model_dump())
    session.add(sensor)
    await session.commit()
    await session.refresh(sensor)
    return sensor


@app.get("/sensors", response_model=list[SensorResponse])
async def list_sensors(
    session: AsyncSession = Depends(get_session),
) -> list[Sensor]:
    result = await session.scalars(select(Sensor).order_by(Sensor.id))
    return list(result.all())


@app.get("/sensors/{sensor_id}", response_model=SensorResponse)
async def get_sensor(
    sensor_id: int,
    session: AsyncSession = Depends(get_session),
) -> Sensor:
    sensor = await session.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor not found")
    return sensor


@app.patch("/sensors/{sensor_id}", response_model=SensorResponse)
async def update_sensor(
    sensor_id: int,
    payload: SensorUpdate,
    session: AsyncSession = Depends(get_session),
) -> Sensor:
    sensor = await session.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sensor, field, value)
    await session.commit()
    await session.refresh(sensor)
    return sensor


@app.delete("/sensors/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sensor(
    sensor_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    sensor = await session.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor not found")
    await session.delete(sensor)
    await session.commit()


@app.post(
    "/sensors/{sensor_id}/readings",
    response_model=ReadingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_reading(
    sensor_id: int,
    payload: ReadingCreate,
    session: AsyncSession = Depends(get_session),
) -> Reading:
    sensor = await session.get(Sensor, sensor_id)
    if not sensor:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor not found")
    if not sensor.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sensor is inactive")

    reading = Reading(
        sensor_id=sensor_id,
        value=payload.value,
        measured_at=(
            _utc_naive(payload.measured_at)
            if payload.measured_at
            else datetime.now(timezone.utc).replace(tzinfo=None)
        ),
    )
    session.add(reading)
    await session.commit()
    await session.refresh(reading)

    alert = app.state.worker.evaluate(sensor, reading)
    await app.state.worker.broadcast(
        {
            "sensor_id": sensor_id,
            "sensor_code": sensor.code,
            "unit": sensor.unit,
            "value": reading.value,
            "measured_at": reading.measured_at.isoformat(),
            "alert": alert,
        }
    )
    return reading


@app.get("/readings", response_model=list[ReadingResponse])
async def list_readings(
    sensor_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[Reading]:
    query = select(Reading).order_by(Reading.measured_at.desc()).limit(limit)
    if sensor_id is not None:
        query = query.where(Reading.sensor_id == sensor_id)
    result = await session.scalars(query)
    return list(result.all())


@app.get("/sensors/{sensor_id}/readings/latest", response_model=ReadingResponse)
async def latest_reading(
    sensor_id: int,
    session: AsyncSession = Depends(get_session),
) -> Reading:
    if not await session.get(Sensor, sensor_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor not found")
    reading = await session.scalar(
        select(Reading)
        .where(Reading.sensor_id == sensor_id)
        .order_by(Reading.measured_at.desc())
    )
    if not reading:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No readings found")
    return reading


@app.get("/sensors/{sensor_id}/readings", response_model=list[ReadingResponse])
async def sensor_readings(
    sensor_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[Reading]:
    if not await session.get(Sensor, sensor_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sensor not found")

    query = (
        select(Reading)
        .where(Reading.sensor_id == sensor_id)
        .order_by(Reading.measured_at.desc())
        .limit(limit)
    )
    if start:
        query = query.where(Reading.measured_at >= start)
    if end:
        query = query.where(Reading.measured_at <= end)
    result = await session.scalars(query)
    return list(result.all())


@app.websocket("/ws/readings")
async def reading_notifications(websocket: WebSocket) -> None:
    await app.state.worker.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        app.state.worker.disconnect(websocket)
