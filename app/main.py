from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from shapely.geometry import shape
from .schemas import NDVIRequest, NDVIResponse
from .stac import search_scenes
from .processing import process_ndvi, get_grid

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)
app = FastAPI(title="NDVI por polígono", version="0.1.0")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(ROOT / "static" / "index.html")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/ndvi", response_model=NDVIResponse)
def compute_ndvi(req: NDVIRequest):
    try:
        geom = shape(req.geometry)
        get_grid(req.geometry)  # validate before accessing STAC
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("Se requiere un polígono")
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        scenes = search_scenes(req.geometry, req.date_from, req.date_to,
                               req.max_scene_cloud, req.max_scenes)
        if not scenes:
            raise HTTPException(status_code=404, detail="No se encontraron escenas para las fechas y filtros")
        job_id = uuid4().hex
        data = process_ndvi(req.geometry, scenes, OUTPUT_DIR, job_id)
        return NDVIResponse(job_id=job_id, **data)
    except HTTPException:
        raise
    except Exception as exc:
        # Para demo: no filtrar URLs SAS ni detalles internos en los errores.
        raise HTTPException(status_code=502, detail=f"No se pudo consultar/procesar Sentinel-2 ({type(exc).__name__})") from exc
