# NDVI por polígono — FastAPI + Sentinel-2

Demo educativa: dibujar un polígono en Leaflet y obtener NDVI a 10 m, fechas de las escenas, nubosidad de tile y nubosidad localizada en el AOI. El backend descubre escenas Sentinel-2 L2A a través de STAC Planetary Computer y lee las bandas COG B04, B08 y SCL sin bajar escenas completas.

## Estructura

- `app/main.py`: endpoints y manejo de errores.
- `app/schemas.py`: entrada y salida Pydantic.
- `app/stac.py`: búsqueda STAC y firma de URLs.
- `app/processing.py`: reproyección, máscara de nubes, NDVI, mosaico y GeoTIFF/PNG.
- `static/index.html`: visual simple Leaflet + Leaflet.draw.
- `tests/test_api.py`: pruebas sin conexión remota.

## Instalación (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visitar http://127.0.0.1:8000 para dibujar el polígono; documentación HTTP en http://127.0.0.1:8000/docs.

## Instalación (Linux/macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Ejemplo REST

```bash
curl -X POST http://127.0.0.1:8000/api/ndvi \
  -H 'Content-Type: application/json' \
  -d '{"geometry":{"type":"Polygon","coordinates":[[[-60.72,-31.65],[-60.71,-31.65],[-60.71,-31.64],[-60.72,-31.64],[-60.72,-31.65]]]},"date_from":"2026-06-01","date_to":"2026-06-30","max_scene_cloud":80,"max_scenes":8}'
```

## Reglas de la demo

- Coordenadas del polígono en GeoJSON WGS84 (`[longitud, latitud]`), sin huecos autointersectados.
- Resolución 10 m, malla UTM calculada según centroide, hasta 1 millón de píxeles.
- Selección de hasta 8 escenas, ordenadas por fecha descendente y menor nubosidad total del tile en una misma fecha. Una escena anterior puede completar huecos: por ello el mosaico puede incluir fechas distintas.
- `eo:cloud_cover` es la nubosidad *del tile* reportada en STAC; `cloud_cover_aoi_percent` de escena es el porcentaje clasificado SCL 8/9/10 **dentro del polígono cubierto por esa escena**, no el mismo número.
- Máscara SCL NDVI: se incluyen clases 4, 5, 6 y 7; se excluyen sombras (3), nubes (8–10), nieve/hielo (11), nodata/saturación. Los datos SCL a 20 m se reproyectan por vecino cercano a la malla de 10 m.
- `cloud_cover_aoi_percent` global cuenta la nubosidad residual del mosaico entre píxeles observados: nubes sin sustitución válida de otra escena / píxeles observados. No es la nubosidad original media de las escenas, y no es `100 - cobertura válida`.
- GeoTIFF NDVI float32 EPSG UTM con nodata=-9999. PNG RGBA georreferenciada mediante bounding box WGS84 para Leaflet. En zonas amplias la superposición de PNG con límites WGS84 es aproximada debido a la reproyección del rectángulo UTM; para producción servir teselas/reproyectar a EPSG:3857.
- Los resultados se guardan localmente sin limpieza automática. Sin autenticación, colas de tareas o límites de tasa: solo para desarrollo local.

## Pruebas

```bash
pytest -q
```

## Limitaciones

La disponibilidad/latencia de las escenas depende de Planetary Computer. La API tiene acceso público sujeto a políticas y cambios del proveedor. La descarga de COG remotos requiere acceso a internet y configuración GDAL/rasterio adecuada. No hay garantía de cobertura total ni una única fecha para un mosaico. Para producto operacional, separar trabajos asíncronos, controlar cuotas, crear COG de salida y teselas XYZ, cachear imágenes, autenticación y métricas adicionales.
