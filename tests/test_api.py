from fastapi.testclient import TestClient
from app.main import app
from app.processing import get_grid
import pytest

client = TestClient(app)
POLYGON = {"type":"Polygon","coordinates":[[[-60.72,-31.65],[-60.71,-31.65],[-60.71,-31.64],[-60.72,-31.64],[-60.72,-31.65]]]}

def test_health():
    assert client.get('/health').json() == {"status":"ok"}

def test_invalid_dates():
    response=client.post('/api/ndvi',json={"geometry":POLYGON,"date_from":"2026-06-30","date_to":"2026-06-01"})
    assert response.status_code == 422

def test_grid():
    crs, transform, width, height, mask=get_grid(POLYGON)
    assert crs.to_epsg() == 32720 or crs.to_epsg() == 32721
    assert mask.any() and width>0 and height>0

def test_too_big():
    large={"type":"Polygon","coordinates":[[[-61,-32],[-60,-32],[-60,-31],[-61,-31],[-61,-32]]]}
    with pytest.raises(ValueError,match="demasiado grande"):
        get_grid(large)
