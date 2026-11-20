from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SensorCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    sensor_type: str = Field(min_length=1, max_length=64)
    unit: str = Field(min_length=1, max_length=32)
    location: str | None = Field(default=None, max_length=128)
    min_value: float | None = None
    max_value: float | None = None
    active: bool = True

    @model_validator(mode="after")
    def validate_thresholds(self) -> "SensorCreate":
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError("min_value must be less than or equal to max_value")
        return self


class SensorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    sensor_type: str | None = Field(default=None, min_length=1, max_length=64)
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    location: str | None = Field(default=None, max_length=128)
    min_value: float | None = None
    max_value: float | None = None
    active: bool | None = None

    @model_validator(mode="after")
    def validate_thresholds(self) -> "SensorUpdate":
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError("min_value must be less than or equal to max_value")
        return self


class SensorResponse(SensorCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ReadingCreate(BaseModel):
    value: float = Field(allow_inf_nan=False)
    measured_at: datetime | None = None


class ReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sensor_id: int
    value: float
    measured_at: datetime
