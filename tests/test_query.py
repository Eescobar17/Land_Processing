import requests
import itertools
import json
import geopandas as gpd
import glob
import os
from pathlib import Path
import os
import traceback
import pandas as pd
import numpy as np
from shapely.ops import unary_union
from datetime import datetime, timedelta
import geopandas as gpd
from shapely.geometry import shape, mapping, Polygon
import numpy as np
import matplotlib.pyplot as plt
import os
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
        data_path = script_dir.parent / "data" / "temp" / "source"  # Ruta a la carpeta con los archivos

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

def get_footprint_from_feature(feature):
    """
    Extrae la huella (footprint) de una característica (feature) de Landsat.
    
    Args:
        feature: Característica de Landsat (de la API STAC)
        
    Returns:
        shapely.geometry.Polygon: Huella de la imagen
    """

    # Intentar obtener la huella directamente de los metadatos
    if 'geometry' in feature:
        return shape(feature['geometry'])
    
    # Si no está directamente, intentar construirla a partir de las propiedades
    if 'properties' in feature and all(k in feature['properties'] for k in ['landsat:bounds_north', 'landsat:bounds_south', 'landsat:bounds_east', 'landsat:bounds_west']):
        props = feature['properties']
        north = props['landsat:bounds_north']
        south = props['landsat:bounds_south']
        east = props['landsat:bounds_east']
        west = props['landsat:bounds_west']
        
        # Crear un polígono rectangular a partir de las coordenadas
        footprint = Polygon([
            (west, north),
            (east, north),
            (east, south),
            (west, south),
            (west, north)
        ])
        return footprint
    
    # Si no podemos determinar la huella, devolver None
    return None

def analyze_coverage(features, min_area):
    """
    Analiza la cobertura del polígono por las escenas Landsat con enfoque en Path/Row.
    Prioriza cobertura espacial, luego minimiza nubosidad y finalmente ajusta coherencia temporal.
    
    Args:
        polygon_file: Ruta al archivo GeoJSON o Shapefile del polígono
        features: Lista de características (features) de Landsat
        
    Returns:
        dict: Información de cobertura incluyendo porcentaje y escenas necesarias
    """
    
    print("Analizando cobertura con enfoque optimizado en Path/Row...")

    # Ruta basada en la ubicación del script
    script_dir = Path(__file__).parent  # Carpeta donde está query.py
    data_path = script_dir.parent / "data" / "temp" / "source"  # Ruta a la carpeta con los archivos

    # Buscar archivos con extensión .geojson y .shp
    files = sorted(
        glob.glob(str(data_path / "*.geojson")) + glob.glob(str(data_path / "*.shp")), 
        key=os.path.getmtime, 
        reverse=True
    )

    if not files:
        raise FileNotFoundError(f"No se encontró ningún archivo en: {data_path}")

    # Leer el polígono
    gdf_polygon = gpd.read_file(files[0])
    polygon = gdf_polygon.geometry.iloc[0]
    polygon_area = polygon.area
    
    # Lista para almacenar información de todas las escenas
    all_scenes = []
    
    # Extraer información de todas las escenas
    for i, feature in enumerate(features):
        footprint = get_footprint_from_feature(feature)
        if not footprint:
            continue
        
        # Obtener información de la escena
        props = feature.get('properties', {})
        scene_id = feature.get('id', f'Escena {i+1}')
        path = props.get('landsat:wrs_path', 'N/A')
        row = props.get('landsat:wrs_row', 'N/A')
        date_str = props.get('datetime', '')
        cloud = props.get('eo:cloud_cover', 100.0)  # Valor predeterminado alto
        
        # Convertir fecha a formato datetime
        try:
            date_obj = datetime.strptime(date_str[:10], '%Y-%m-%d') if date_str else None
        except:
            date_obj = None
        
        # Calcular intersección con el polígono
        intersection = polygon.intersection(footprint)
        intersection_area = intersection.area
        coverage_percent = (intersection_area / polygon_area) * 100

        # print("\n\n")
        # print(intersection)
        # print(coverage_percent)
        # print("\n\n")
        
        # Incluir todas las escenas que tengan alguna intersección significativa con el polígono
        if coverage_percent >= min_area:  # Umbral mínimo para descartar escenas y ahorrar recursos
            path_row = f"{path}_{row}"
            
            all_scenes.append({
                'id': scene_id,
                'path': path,
                'row': row,
                'path_row': path_row,
                'date_str': date_str[:10] if isinstance(date_str, str) else '',
                'date_obj': date_obj,
                'cloud_cover': cloud,
                'coverage_percent': coverage_percent,
                'footprint': footprint,
                'intersection_area': intersection_area
            })
    
    # Convertir a DataFrame para facilitar análisis
    scenes_df = pd.DataFrame(all_scenes)
    
    if scenes_df.empty:
        print("No se encontraron escenas con intersección significativa con el polígono.")
        return {
            'total_coverage_percent': 0,
            'coverage_by_scene': pd.DataFrame(),
            'scenes_needed': [],
            'uncovered_percent': 100
        }
    

    # Parámetros
    window_days = 120
    delete_out_range = False  # Si True, elimina los path_row que no pueden ajustarse a la ventana

    # Ordenar por menor cloud_cover
    scenes_df = scenes_df.sort_values(by=["cloud_cover"])

    # Conjunto para almacenar los path_row seleccionados
    selected_path_rows = set()
    best_rows = []

    # Iterar sobre los registros priorizando menor cloud_cover
    for _, row in scenes_df.iterrows():
        if row["path_row"] in selected_path_rows:
            continue  # Si ya seleccionamos este path_row, lo ignoramos
        
        # Verificar si al agregar este path_row la ventana de tiempo se respeta
        temp_selection = best_rows + [row]
        min_date = min([r["date_obj"] for r in temp_selection])
        max_date = max([r["date_obj"] for r in temp_selection])
        
        if (max_date - min_date).days > window_days:
            if delete_out_range:
                continue  # Si la opción está activa, descartamos este path_row
            else:
                break  # Si no, terminamos la selección sin incluirlo
        
        # Agregar a la selección
        selected_path_rows.add(row["path_row"])
        best_rows.append(row)

    # Convertir resultado a DataFrame
    best_df = pd.DataFrame(best_rows)

    final_coverage = float(best_df["intersection_area"].sum())

    print(f"NOTA: Se cubrió el {final_coverage*100:.2f}% del área del polígono")
    
    return best_df



config = {
    "file_path": "../../data/temp/source/source_file.*",
    "import_mode": True,  
    "generate_mode": False,
    "path_row_mode": False,
    "path": "010",
    "row": "054",
    "start_date": "2025-01-01",
    "end_date": "2025-03-31",
    "diff_date_enabled": False,
    "diff_start_date": "",
    "diff_end_date": "",
    "cloud_cover": "100",
    "selected_indices":["NDVI"],
    "imported_file": "",
    "platform": ["LANDSAT_8"],
    "collections": ["landsat-c2l2-sr"],
    "limit": 100
}

query = generate_landsat_query(**config)
features = fetch_stac_server(query)
df = analyze_coverage(features, 0)

print(len(df))
print("\n\n")
print(df)






