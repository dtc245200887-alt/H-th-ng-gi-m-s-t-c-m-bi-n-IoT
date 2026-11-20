# IoT Sensor Monitoring

FastAPI application implementing sensor registration, reading ingestion, storage,
alert evaluation, realtime WebSocket notifications, and reading history.

## Run

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://localhost:8000> for the dashboard and
<http://localhost:8000/docs> for the Swagger API.

## API

- `POST /sensors`: register sensor
- `GET /sensors`: list sensors
- `GET /sensors/{id}`: get sensor
- `PATCH /sensors/{id}`: update sensor
- `DELETE /sensors/{id}`: delete sensor
- `POST /sensors/{id}/readings`: ingest reading
- `GET /readings`: list recent readings
- `GET /sensors/{id}/readings/latest`: latest reading
- `GET /sensors/{id}/readings?start=&end=&limit=`: historical readings
- `WS /ws/readings`: realtime notifications
