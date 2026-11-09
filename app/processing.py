"""Mosaico de NDVI sobre grilla UTM de 10 m con máscaras SCL."""
from pathlib import Path
import math
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin, array_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform as transform_shape
from PIL import Image

from .schemas import SceneInfo

# SCL: 4 vegetation, 5 bare ground, 6 water, 7 unclassified.
# 8 medium-cloud, 9 high-cloud, 10 cirrus; 3 = cloud shadow.
CLEAR_SCL = [4, 5, 6, 7]
CLOUD_SCL = [8, 9, 10]
BAD_SCL = [0, 1, 3, 8, 9, 10, 11]


def get_grid(geometry):
    polygon = shape(geometry)
    if polygon.is_empty or not polygon.is_valid or polygon.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("Geometría inválida: se necesita un Polygon/MultiPolygon válido")
    xmin, ymin, xmax, ymax = polygon.bounds
    if not (-180 <= xmin <= 180 and -180 <= xmax <= 180 and -85 <= ymin <= 85 and -85 <= ymax <= 85):
        raise ValueError("Coordenadas fuera del rango admitido (EPSG:4326)")
    lon, lat = polygon.centroid.x, polygon.centroid.y
    zone = min(60, max(1, math.floor((lon + 180) / 6) + 1))
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    crs = CRS.from_epsg(epsg)
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    geom_utm = transform_shape(tr.transform, polygon)
    left, bottom, right, top = geom_utm.bounds
    # Alinear grilla al múltiplo de 10 m para combinar escenas sin desplazamientos.
    left, bottom = math.floor(left / 10) * 10, math.floor(bottom / 10) * 10
    right, top = math.ceil(right / 10) * 10, math.ceil(top / 10) * 10
    width, height = int((right-left)/10), int((top-bottom)/10)
    if width < 1 or height < 1 or width * height > 1_000_000:
        raise ValueError("Área demasiado grande para la demo (máximo 1 millón de píxeles a 10 m)")
    transform = from_origin(left, top, 10, 10)
    inside = geometry_mask([mapping(geom_utm)], out_shape=(height, width), transform=transform, invert=True)
    return crs, transform, width, height, inside


def read_asset(item, asset_name, crs, transform, width, height, resampling):
    if asset_name not in item.assets:
        raise ValueError(f"La escena {item.id} no contiene {asset_name}")
    with rasterio.open(item.assets[asset_name].href) as src:
        with WarpedVRT(src, crs=crs, transform=transform, width=width,
                       height=height, resampling=resampling, nodata=src.nodata) as vrt:
            return vrt.read(1, masked=True)


def render_png(ndvi, valid, dest: Path):
    """Paleta simple marrón/amarillo/verde; fuera de AOI y sin datos transparente."""
    h, w = ndvi.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    x = np.clip((np.nan_to_num(ndvi, nan=-1) + 1) / 2, 0, 1)
    # 0..0.5 marrón -> amarillo; 0.5..1 amarillo -> verde.
    stops = np.array([[139, 76, 43], [245, 224, 99], [29, 125, 62]], dtype=float)
    t = x * 2
    low = np.clip(t.astype(np.int32), 0, 1)
    frac = (t - low)[..., None]
    rgba[..., :3] = (stops[low] * (1-frac) + stops[low+1] * frac).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 215, 0).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(dest)


def process_ndvi(geometry, items, output_dir: Path, job_id: str):
    crs, transform, width, height, inside = get_grid(geometry)
    result = np.full((height, width), np.nan, dtype="float32")
    remaining = inside.copy()
    cloud_seen = np.zeros((height, width), dtype=bool)
    observed = np.zeros((height, width), dtype=bool)
    sources = []
    for item in items:
        if not remaining.any():
            break
        red = read_asset(item, "B04", crs, transform, width, height, Resampling.bilinear)
        nir = read_asset(item, "B08", crs, transform, width, height, Resampling.bilinear)
        scl = read_asset(item, "SCL", crs, transform, width, height, Resampling.nearest)
        scl_data = np.asarray(scl.filled(0))
        data_ok = (~np.ma.getmaskarray(red)) & (~np.ma.getmaskarray(nir)) & (~np.ma.getmaskarray(scl))
        footprint = inside & data_ok & (scl_data >= 2) & (scl_data <= 11)
        observed |= footprint
        cloud = footprint & np.isin(scl_data, CLOUD_SCL)
        cloud_seen |= cloud
        n_footprint = int(footprint.sum())
        cloud_pct = round(100 * cloud.sum() / n_footprint, 2) if n_footprint else None
        red_data = np.asarray(red.filled(0), dtype="float32")
        nir_data = np.asarray(nir.filled(0), dtype="float32")
        denominator = nir_data + red_data
        ok = remaining & footprint & np.isin(scl_data, CLEAR_SCL) & (denominator > 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            ndvi = (nir_data - red_data) / denominator
        result[ok] = np.clip(ndvi[ok], -1, 1)
        remaining[ok] = False
        sources.append(SceneInfo(
            id=item.id,
            datetime=item.datetime.isoformat(),
            cloud_cover_scene_percent=item.properties.get("eo:cloud_cover"),
            cloud_cover_aoi_percent=cloud_pct,
            pixels_contributed=int(ok.sum()),
        ))

    valid = inside & np.isfinite(result)
    inside_count = int(inside.sum())
    if inside_count == 0:
        raise ValueError("El polígono es demasiado pequeño para la resolución de 10 m")
    output_dir.mkdir(parents=True, exist_ok=True)
    tiff_path = output_dir / f"{job_id}.tif"
    png_path = output_dir / f"{job_id}.png"
    with rasterio.open(tiff_path, "w", driver="GTiff", width=width, height=height,
                       count=1, dtype="float32", crs=crs, transform=transform,
                       nodata=-9999.0, compress="deflate") as dst:
        dst.write(np.where(valid, result, -9999.0).astype("float32"), 1)
    render_png(result, valid, png_path)
    left, bottom, right, top = array_bounds(height, width, transform)
    bounds = list(transform_bounds(crs, "EPSG:4326", left, bottom, right, top, densify_pts=21))
    vals = result[valid]
    # Cloud percentage is measured over the AOI cells observed in at least one source;
    # cloudy cells eventually replaced by clear observations do not count as final cloud.
    final_cloud = cloud_seen & ~valid
    cloud_pct = round(100 * final_cloud.sum() / observed.sum(), 2) if observed.any() else None
    dates = list(dict.fromkeys(s.datetime[:10] for s in sources if s.pixels_contributed > 0))
    return {
        "ndvi_mean": round(float(vals.mean()), 4) if vals.size else None,
        "ndvi_min": round(float(vals.min()), 4) if vals.size else None,
        "ndvi_max": round(float(vals.max()), 4) if vals.size else None,
        "valid_coverage_percent": round(100 * valid.sum() / inside_count, 2),
        "cloud_cover_aoi_percent": cloud_pct,
        "image_dates": dates,
        "scenes": sources,
        "bounds_wgs84": bounds,
        "png_url": f"/outputs/{job_id}.png",
        "geotiff_url": f"/outputs/{job_id}.tif",
    }
