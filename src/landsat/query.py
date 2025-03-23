import requests
import itertools
import json
import geopandas as gpd
import glob
import os
from pathlib import Path

def generate_landsat_query(
        file_path,
        import_mode,
        generate_mode,
        path_row_mode,
        path,
        row,
        start_date,
        end_date,
        diff_date_enabled,
        diff_start_date,
        diff_end_date,
        cloud_cover,
        selected_indices,
        imported_file,
        platform=["LANDSAT_8"],
        collections=["landsat-c2l2-sr"],
        limit=100
    ):

    """
    Genera una consulta para la API LandsatLook desde un GeoJSON o Shapefile.
    """  

    # Crear el query dependiendo del modo de importación
    if path_row_mode:
        query = {
            "collections": collections,
            "query": {
                "eo:cloud_cover": {"lte": cloud_cover},
                "platform": {"in": platform},
                "landsat:collection_category": {"in": ["T1", "T2", "RT"]},
                "landsat:wrs_path": {"eq": str(path).zfill(3)},
                "landsat:wrs_row": {"eq": str(row).zfill(3)}
            },
            "datetime": f"{start_date}T00:00:00.000Z/{end_date}T23:59:59.999Z",
            "page": 1,
            "limit": limit
        }
    else:
        # Ruta basada en la ubicación del script
        script_dir = Path(__file__).parent  # Carpeta donde está query.py
        data_path = script_dir.parent.parent / "data" / "temp" / "source"  # Ruta a la carpeta con los archivos

        # Buscar archivos con extensión .geojson y .shp
        files = sorted(
            glob.glob(str(data_path / "*.geojson")) + glob.glob(str(data_path / "*.shp")), 
            key=os.path.getmtime, 
            reverse=True
        )

        if not files:
            raise FileNotFoundError(f"No se encontró ningún archivo en: {data_path}")

        # Cargar el archivo más reciente
        gdf = gpd.read_file(files[0])

        # Obtener la geometría en formato GeoJSON
        geom = json.loads(gdf.to_json())['features'][0]['geometry']

        query = {
            "intersects": geom,
            "collections": collections,
            "query": {
                "eo:cloud_cover": {"lte": cloud_cover},
                "platform": {"in": platform},
                "landsat:collection_category": {"in": ["T1", "T2", "RT"]}
            },
            "datetime": f"{start_date}T00:00:00.000Z/{end_date}T23:59:59.999Z",
            "page": 1,
            "limit": limit
        }
    
    return query

def fetch_stac_server(query):
    """
    Consulta el backend de stac-server (STAC).
    Esta función gestiona la paginación.
    La consulta es un diccionario de Python que se pasa como JSON a la solicitud.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip",
        "Accept": "application/geo+json",
    }

    url = f"https://landsatlook.usgs.gov/stac-server/search"
    data = requests.post(url, headers=headers, json=query).json()
    error = data.get("message", "")
    if error:
        raise Exception(f"STAC-Server failed and returned: {error}")

    context = data.get("context", {})
    if not context.get("matched"):
        return []
    print(context)

    features = data["features"]
    if data["links"]:
        query["page"] += 1
        query["limit"] = context["limit"]

        features = list(itertools.chain(features, fetch_stac_server(query)))

    return features