from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class NDVIRequest(BaseModel):
    geometry: dict = Field(description="GeoJSON Polygon o MultiPolygon en EPSG:4326")
    date_from: date
    date_to: date
    max_scene_cloud: float = Field(default=80, ge=0, le=100)
    max_scenes: int = Field(default=8, ge=1, le=20)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.date_to < self.date_from:
            raise ValueError("date_to debe ser mayor o igual que date_from")
        if (self.date_to - self.date_from).days > 90:
            raise ValueError("La demo admite ventanas de 90 días como máximo")
        return self

class SceneInfo(BaseModel):
    id: str
    datetime: str
    cloud_cover_scene_percent: float | None
    cloud_cover_aoi_percent: float | None
    pixels_contributed: int

class NDVIResponse(BaseModel):
    job_id: str
    status: Literal["ok"] = "ok"
    satellite: str = "Sentinel-2 L2A"
    resolution_m: int = 10
    ndvi_mean: float | None
    ndvi_min: float | None
    ndvi_max: float | None
    valid_coverage_percent: float
    cloud_cover_aoi_percent: float | None
    image_dates: list[str]
    scenes: list[SceneInfo]
    png_url: str
    geotiff_url: str
    bounds_wgs84: list[float]  # [west, south, east, north]
