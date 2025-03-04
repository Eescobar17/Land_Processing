import requests
import itertools
import json
import geopandas as gpd

def generate_landsat_query(file_path, start_date, end_date, cloud_cover=5, platform=["LANDSAT_8"], collections=["landsat-c2l2-sr"], limit=100):
    """
    Generates a query for the LandsatLook API from a GeoJSON or Shapefile.

    :param file_path: Path to the GeoJSON or Shapefile.
    :param start_date: Start date in 'YYYY-MM-DD' format.
    :param end_date: End date in 'YYYY-MM-DD' format.
    :param cloud_cover: Maximum cloud cover percentage (default is 5%).
    :param platform: List of Landsat platforms (default is ['LANDSAT_8']).
    :param collections: List of Landsat collections (default is ['landsat-c2l2-sr']).
    :param limit: Maximum number of results per page (default is 100).
    :return: Dictionary with the generated query.
    """  

    # Cargar el archivo en un GeoDataFrame
    gdf = gpd.read_file(file_path)
    
    # Obtener la geometría en formato GeoJSON
    geom = json.loads(gdf.to_json())['features'][0]['geometry']
    
    # Crear el query
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
    Queries the stac-server (STAC) backend.
    This function handles pagination.
    query is a python dictionary to pass as json to the request.
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