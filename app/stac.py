from datetime import timedelta
import planetary_computer
from pystac_client import Client

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


def search_scenes(geometry: dict, date_from, date_to, max_cloud: float, max_scenes: int):
    catalog = Client.open(STAC_URL)
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        intersects=geometry,
        datetime=f"{date_from.isoformat()}/{(date_to + timedelta(days=1)).isoformat()}",
        query={"eo:cloud_cover": {"lte": max_cloud}},
        max_items=200,
    )
    items = list(search.items())
    # Priorizar fecha reciente y, dentro de la misma fecha, menor nubosidad del tile.
    items.sort(key=lambda i: (i.datetime.date(), -(i.properties.get("eo:cloud_cover") or 0)), reverse=True)
    chosen = items[:max_scenes]
    return [planetary_computer.sign(item) for item in chosen]
