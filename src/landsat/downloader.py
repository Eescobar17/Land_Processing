import os
import requests
import json
from bs4 import BeautifulSoup
from .config import USGS_USERNAME, USGS_PASSWORD
from pathlib import Path
import traceback

LOGIN_URL = "https://ers.cr.usgs.gov/login"

def login_usgs():
    """ Logs into the USGS system and returns an authenticated session."""
    session = requests.Session()
    
    # Get the login page to extract the CSRF token
    response = session.get(LOGIN_URL)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html.parser')
    csrf_token = soup.find('input', attrs={'name': 'csrf'})['value']

    # Login form data
    login_data = {
        "username": USGS_USERNAME,
        "password": USGS_PASSWORD,
        "csrf": csrf_token
    }

    # Send the login request
    login_response = session.post(LOGIN_URL, data=login_data)
    login_response.raise_for_status()

    if login_response.status_code == 200:
        print("Successfully logged into USGS")
    else:
        print("Authentication failed")

    return session
 
def determine_required_bands(selected_indices):
    """Determina las bandas requeridas y sus colecciones para los índices seleccionados."""
    required_bands = {}
    
    for index in selected_indices:
        if index == "NDVI":
            required_bands.update({"B4": "sr", "B5": "sr"})  # Red, NIR
        elif index == "NDWI":
            required_bands.update({"B3": "sr", "B5": "sr"})  # Green, NIR
        elif index == "NDSI":
            required_bands.update({"B3": "sr", "B6": "sr"})  # Green, SWIR
        elif index == "BSI":
            required_bands.update({"B2": "sr", "B4": "sr", "B5": "sr", "B6": "sr"})  # Blue, Red, NIR, SWIR1
        elif index == "LST":
            # Para LST necesitamos la banda térmica B10 de la colección ST y bandas ópticas para NDVI
            required_bands.update({"B10": "st", "B4": "sr", "B5": "sr"})  # TIRS1, Red, NIR para LST
    
    if required_bands:
        print(f"\nÍndices seleccionados: {', '.join(selected_indices)}")
        print(f"Bandas requeridas: {', '.join(required_bands.keys())}")
        
        # Mostrar qué colecciones se necesitan
        st_bands = [band for band, collection in required_bands.items() if collection == "st"]
        sr_bands = [band for band, collection in required_bands.items() if collection == "sr"]
        
        if sr_bands:
            print(f"Bandas SR (colección landsat-c2l2-sr): {', '.join(sr_bands)}")
        if st_bands:
            print(f"Bandas ST (colección landsat-c2l2-st): {', '.join(st_bands)}")
    else:
        raise Exception("No se encontraron índices seleccionados.")
    
    return required_bands

def get_collection_from_feature(feature):
    """Determina a qué colección pertenece un feature basado en su ID o colección explícita."""
    # Si tiene el campo colección explícito, usamos ese
    if "collection" in feature:
        return feature["collection"]
    
    # Si no, intentamos inferirlo del ID o propiedades
    feature_id = feature.get("id", "").lower()
    
    if "_sr_" in feature_id or feature_id.endswith("_sr"):
        return "landsat-c2l2-sr"
    elif "_st_" in feature_id or feature_id.endswith("_st"):
        return "landsat-c2l2-st"
    
    # También podemos verificar en las propiedades
    if "properties" in feature:
        collection_prop = feature["properties"].get("collection", "").lower()
        if "st" in collection_prop:
            return "landsat-c2l2-st"
        elif "sr" in collection_prop:
            return "landsat-c2l2-sr"
    
    # Por defecto, asumimos SR
    return "landsat-c2l2-sr"

def construct_band_url(base_url, band, collection_type):
    """
    Construye una URL para una banda específica basada en una URL base conocida.
    Ajusta los sufijos de colección (SR/ST) según sea necesario.
    """
    # Identificar qué patrones de colección están en la URL base
    sr_pattern = "_SR_"
    st_pattern = "_ST_"
    
    # Determinar el patrón a buscar y el patrón a usar
    search_pattern = st_pattern if "_ST_" in base_url else sr_pattern if "_SR_" in base_url else None
    replace_pattern = f"_{collection_type.upper()}_"
    
    if not search_pattern:
        # Si no encontramos ningún patrón, intentar construir la URL de otra manera
        # Buscar el último segmento que contenga un indicador de banda (B1, B2, etc.)
        segments = base_url.split('/')
        last_segment = segments[-1]
        
        # Buscar patrones como B1, B2, etc.
        if "_B" in last_segment:
            # Reemplazar la parte _B{N} con la nueva banda
            parts = last_segment.split('_B')
            new_segment = f"{parts[0]}_{collection_type.upper()}_B{band[1:]}.TIF"
            segments[-1] = new_segment
            return '/'.join(segments)
    else:
        # Si encontramos un patrón, reemplazarlo y también ajustar la banda
        if search_pattern in base_url and band:
            # Primero reemplazamos el indicador de colección
            url = base_url.replace(search_pattern, replace_pattern)
            
            # Luego reemplazamos la indicación de banda
            # Buscar patrones como B1, B2, etc.
            band_part = "_B" + base_url.split('_B')[-1].split('.')[0]
            new_band_part = f"_B{band[1:]}"
            url = url.replace(band_part, new_band_part)
            
            return url
    
    # Si llegamos aquí, no pudimos construir la URL
    return None

def extract_scene_info(feature):
    """
    Extrae información básica de identificación de escena de un feature.
    """
    scene_id = feature.get('id', '')
    collection = get_collection_from_feature(feature)
    
    # Extraer información de propiedades
    props = feature.get('properties', {})
    path = props.get('landsat:wrs_path', '')
    row = props.get('landsat:wrs_row', '')
    date = props.get('datetime', '')[:10] if props.get('datetime') else ''
    
    # Extraer información del scene_id si está disponible
    parts = scene_id.split('_')
    if len(parts) >= 3 and parts[0].startswith('LC'):
        if not path and len(parts) > 2:
            path_row = parts[2]
            if len(path_row) == 6:
                path = path_row[:3]
                row = path_row[3:]
    
    return {
        'id': scene_id,
        'collection': collection,
        'path': path,
        'row': row,
        'date': date
    }

def find_matching_feature(features, path, row, date, target_collection):
    """
    Busca un feature que coincida con path, row, fecha y colección específica.
    """
    matching_features = []
    
    for feature in features:
        props = feature.get('properties', {})
        collection = get_collection_from_feature(feature)
        
        if (collection.lower() == target_collection.lower() and
            props.get('landsat:wrs_path') == path and
            props.get('landsat:wrs_row') == row and
            props.get('datetime', '')[:10] == date):
            matching_features.append(feature)
    
    # Devolver el primer match si existe
    return matching_features[0] if matching_features else None

def download_specific_band(session, feature, band, collection, download_path):
    """
    Intenta descargar una banda específica con varios métodos.
    """
    scene_id = feature.get('id', 'unknown')
    msg = f"Intentando descargar banda {band} ({collection}) de {scene_id}"
    print(msg)
    yield msg
    
    if 'assets' not in feature:
        msg = f"Error: La imagen {scene_id} no tiene la clave 'assets'"
        print(msg)
        yield msg
        return False
    
    # Determinar la ruta base y el nombre del archivo
    collection_suffix = "_SR" if collection.lower() == "sr" else "_ST" if collection.lower() == "st" else ""
    base_scene_id = scene_id.split(collection_suffix)[0] if collection_suffix in scene_id else scene_id
    
    # Nombre de archivo para guardar
    file_name = os.path.join(download_path, f"{base_scene_id}_{collection.upper()}_{band}.TIF")
    
    # Lista de posibles variantes para buscar la banda
    band_variants = [
        band,                     # Ejemplo: "B4"
        band.lower(),             # Ejemplo: "b4"
        f"band{band[1:]}",        # Ejemplo: "band4"
        f"band_{band[1:]}",       # Ejemplo: "band_4"
        f"{collection.lower()}_{band.lower()}",  # Ejemplo: "sr_b4"
        f"{band.lower()}"         # Ejemplo: "b4"
    ]
    
    # Buscar la banda en los assets
    download_url = None
    
    # 1. Método 1: Buscar directamente en los assets
    for variant in band_variants:
        if variant in feature['assets'] and 'href' in feature['assets'][variant]:
            download_url = feature['assets'][variant]['href']
            print(f"Encontrada banda {band} como '{variant}'")
            break
    
    # 2. Método 2: Buscar por patrones en nombres de assets
    if not download_url:
        for asset_key, asset_info in feature['assets'].items():
            if 'href' in asset_info and band.lower() in asset_key.lower():
                download_url = asset_info['href']
                print(f"Encontrada banda {band} en asset '{asset_key}'")
                break
    
    # 3. Método 3: Construir URL basada en otra banda encontrada
    if not download_url:
        # Buscar cualquier asset que termine en .TIF para usar como base
        tif_assets = {}
        for asset_key, asset_info in feature['assets'].items():
            if 'href' in asset_info and asset_info['href'].lower().endswith('.tif'):
                tif_assets[asset_key] = asset_info['href']
        
        if tif_assets:
            # Usar el primer asset .TIF como base
            base_asset_key = list(tif_assets.keys())[0]
            base_url = tif_assets[base_asset_key]
            
            # Extraer el nombre del archivo de la URL
            base_filename = base_url.split('/')[-1]
            
            # Construir el nuevo nombre basado en el patrón
            # Ejemplo: LC08_L2SP_009056_20240714_20240722_02_T1_ST_B10.TIF -> LC08_L2SP_009056_20240714_20240722_02_T1_SR_B4.TIF
            parts = base_filename.split('_')
            
            if len(parts) >= 3:
                # Encontrar la parte que tiene B10, B4, etc.
                band_part_index = -1
                for i, part in enumerate(parts):
                    if part.startswith('B') and part[1:].isdigit():
                        band_part_index = i
                        break
                
                # Si encontramos la parte de la banda, reemplazarla
                if band_part_index >= 0:
                    # También buscar y reemplazar SR/ST si es necesario
                    collection_index = -1
                    for i, part in enumerate(parts):
                        if part in ["SR", "ST"]:
                            collection_index = i
                            break
                    
                    # Reemplazar la colección si la encontramos
                    if collection_index >= 0:
                        parts[collection_index] = collection.upper()
                    # Si no la encontramos pero está justo antes de la banda
                    elif band_part_index > 0:
                        parts.insert(band_part_index, collection.upper())
                    
                    # Reemplazar la banda
                    parts[band_part_index] = band
                    
                    # Reconstruir el nombre de archivo
                    new_filename = '_'.join(parts)
                    
                    # Construir la nueva URL
                    download_url = base_url.replace(base_filename, new_filename)
                    
                    # Verificar si la URL existe
                    try:
                        head_response = session.head(download_url)
                        if head_response.status_code == 200:
                            print(f"Construida URL para banda {band}: {download_url}")
                        else:
                            download_url = None
                    except:
                        download_url = None
    
    # 4. Método 4: URL directa basada en patrones conocidos
    if not download_url and 'properties' in feature:
        props = feature['properties']
        if all(k in props for k in ['landsat:wrs_path', 'landsat:wrs_row', 'datetime']):
            try:
                path = props['landsat:wrs_path']
                row = props['landsat:wrs_row']
                date = props['datetime'][:10].replace('-', '')
                
                # Extraer información del ID de la escena
                scene_parts = scene_id.split('_')
                if len(scene_parts) >= 5:
                    satellite = scene_parts[0]  # Ej: LC08
                    level = scene_parts[1]      # Ej: L2SP
                    path_row = path.zfill(3) + row.zfill(3)
                    processing_date = scene_parts[4] if len(scene_parts) > 4 else ""
                    version = scene_parts[5] if len(scene_parts) > 5 else "02"
                    tier = scene_parts[6] if len(scene_parts) > 6 else "T1"
                    
                    # Construir URL directa
                    direct_url = f"https://landsatlook.usgs.gov/data/collection02/level-2/standard/oli-tirs/{date[:4]}/{path}/{row}/"
                    direct_url += f"{satellite}_{level}_{path_row}_{date}_{processing_date}_{version}_{tier}/"
                    direct_url += f"{satellite}_{level}_{path_row}_{date}_{processing_date}_{version}_{tier}_{collection.upper()}_{band}.TIF"
                    
                    # Verificar si existe
                    try:
                        head_response = session.head(direct_url)
                        if head_response.status_code == 200:
                            download_url = direct_url
                            print(f"Construida URL directa para banda {band}: {download_url}")
                    except Exception as e:
                        print(f"Error verificando URL directa: {str(e)}")
            except Exception as e:
                print(f"Error construyendo URL directa: {str(e)}")
    
    # Si no se pudo encontrar la banda, registrar el error
    if not download_url:
        msg = f"No se pudo encontrar la banda {band} en los assets disponibles de esta escena"
        print(msg)
        yield msg
        return False
    
    # Descargar la banda
    try:
        msg = f"Descargando: {os.path.basename(file_name)} desde {download_url}"
        print(msg)
        yield msg

        # Descargar la imagen con autenticación
        with session.get(download_url, stream=True) as response:
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            
            with open(file_name, 'wb') as file:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
                    downloaded += len(chunk)
                    # Mostrar progreso cada 20%
                    if total_size > 0 and downloaded % (total_size // 5) < 8192:
                        percent = (downloaded / total_size) * 100
                        print(f"Progreso: {percent:.1f}%")
                        yield f"Progreso: {percent:.1f}%"
        
        print(f"Descargado: {file_name}")
        return True
    
    except Exception as e:
        print(f"Error al descargar la banda {band}: {str(e)}")
        return False

def download_metadata(session, feature, download_path):
    """Descarga los metadatos de una escena."""
    scene_id = feature.get('id', 'unknown')
    collection = get_collection_from_feature(feature)
    collection_suffix = "_SR" if "sr" in collection.lower() else "_ST" if "st" in collection.lower() else ""
    
    try:
        if "MTL.json" in feature['assets'] and "href" in feature['assets']["MTL.json"]:
            file_name = os.path.join(download_path, f"{scene_id}{collection_suffix}_MTL.json")
            download_url = feature['assets']["MTL.json"]['href']
            print(f"Descargando metadata: {os.path.basename(file_name)}")

            with session.get(download_url, stream=True) as response:
                response.raise_for_status()
                with open(file_name, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
            
            print(f"Metadata descargada: {file_name}")
            return True
        
        return False
    except Exception as e:
        print(f"Error al descargar la metadata: {str(e)}")
        return False

def download_images(features, scenes_needed, required_bands):
    """
    Descarga las bandas necesarias para cada escena, manejando múltiples colecciones.
    """
    # Ruta basada en la ubicación del script
    script_dir = Path(__file__).parent
    download_path = script_dir.parent.parent / "data" / "temp" / "downloads"
    os.makedirs(download_path, exist_ok=True)
    
    # Iniciar sesión en USGS
    try:
        session = login_usgs()
    except Exception as e:
        raise Exception("Fallo al iniciar sesión en USGS.") from e

    # Agrupar escenas por path/row y fecha para evitar duplicados
    scene_groups = {}
    for scene in scenes_needed:
        key = f"{scene['path']}_{scene['row']}_{scene['date']}"
        if key not in scene_groups:
            scene_groups[key] = []
        scene_groups[key].append(scene)
    
    # Descargar bandas para cada grupo de escenas
    for i, (group_key, group_scenes) in enumerate(scene_groups.items()):
        path, row, date = group_key.split("_")
        scene_dir = os.path.join(download_path, f"scene_{path}_{row}_{date}")
        os.makedirs(scene_dir, exist_ok=True)
        
        msg = f"\nProcesando grupo de escenas {i+1}/{len(scene_groups)}: Path={path}, Row={row}, Fecha={date}"
        print(msg)
        yield msg
        
        # Crear registro de bandas descargadas
        downloaded_band_info = {band: False for band in required_bands}
        
        # Procesar primero las escenas ST si estamos buscando bandas ST
        st_needed = any(collection.lower() == 'st' for band, collection in required_bands.items())
        sr_needed = any(collection.lower() == 'sr' for band, collection in required_bands.items())
        
        # Ordenar las escenas: primero las ST si necesitamos bandas ST, luego las SR
        if st_needed:
            group_scenes.sort(key=lambda x: 0 if 'st' in x.get('collection', '').lower() else 1)
        else:
            group_scenes.sort(key=lambda x: 0 if 'sr' in x.get('collection', '').lower() else 1)
        
        # Procesar cada escena del grupo
        for scene in group_scenes:
            scene_id = scene['id']
            collection = scene.get('collection', '').lower()
            
            # Buscar el feature correspondiente
            target_feature = next((f for f in features if f.get('id') == scene_id), None)
            
            if not target_feature:
                print(f"No se encontró la característica para {scene_id}")
                continue
            
            print(f"Procesando escena {scene_id} de colección {collection}")
            
            # Determinar qué bandas descargar de esta escena según su colección
            if 'sr' in collection:
                # De una escena SR, intentar descargar todas las bandas SR requeridas
                sr_bands = [band for band, coll in required_bands.items() 
                           if coll.lower() == 'sr' and not downloaded_band_info[band]]
                
                for band in sr_bands:
                    success = False
                    for result in download_specific_band(session, target_feature, band, 'sr', scene_dir):
                        if isinstance(result, bool):
                            success = result
                        else:
                            yield result
                    
                    if success:
                        downloaded_band_info[band] = True
            
            if 'st' in collection:
                # De una escena ST, intentar descargar todas las bandas ST requeridas
                st_bands = [band for band, coll in required_bands.items() 
                           if coll.lower() == 'st' and not downloaded_band_info[band]]
                
                for band in st_bands:
                    success = False
                    for result in download_specific_band(session, target_feature, band, 'st', scene_dir):
                        if isinstance(result, bool):
                            success = result
                        else:
                            yield result
                    
                    if success:
                        downloaded_band_info[band] = True
                
                # Si tenemos una escena ST y necesitamos bandas SR, buscar la correspondiente escena SR
                if sr_needed and any(not downloaded_band_info[band] for band, coll in required_bands.items() if coll.lower() == 'sr'):
                    # Extraer información para buscar la correspondencia
                    scene_info = extract_scene_info(target_feature)
                    
                    # Buscar un feature SR que coincida
                    matching_sr = find_matching_feature(
                        features, 
                        scene_info['path'], 
                        scene_info['row'], 
                        scene_info['date'], 
                        'landsat-c2l2-sr'
                    )
                    
                    if matching_sr:
                        print(f"Encontrada escena SR correspondiente: {matching_sr.get('id')}")
                        
                        # Descargar las bandas SR pendientes
                        sr_bands = [band for band, coll in required_bands.items() 
                                   if coll.lower() == 'sr' and not downloaded_band_info[band]]
                        
                        for band in sr_bands:
                            success = False
                            for result in download_specific_band(session, matching_sr, band, 'sr', scene_dir):
                                if isinstance(result, bool):
                                    success = result
                                else:
                                    yield result
                            
                            if success:
                                downloaded_band_info[band] = True
                    else:
                        print("No se encontró escena SR correspondiente. Intentando construir URLs...")
                        
                        # Intentar construir URLs para las bandas SR pendientes
                        sr_bands = [band for band, coll in required_bands.items() 
                                   if coll.lower() == 'sr' and not downloaded_band_info[band]]
                        
                        # Obtener una URL base de la escena ST
                        base_url = None
                        for asset_key, asset_info in target_feature['assets'].items():
                            if 'href' in asset_info and asset_info['href'].lower().endswith('.tif'):
                                base_url = asset_info['href']
                                break
                        
                        if base_url:
                            # Convertir la URL base de ST a SR
                            for band in sr_bands:
                                sr_url = base_url.replace('_ST_', '_SR_').replace('_B10', f'_B{band[1:]}')
                                
                                try:
                                    # Verificar si la URL existe
                                    head_response = session.head(sr_url)
                                    if head_response.status_code == 200:
                                        print(f"Construida URL para banda {band}: {sr_url}")
                                        
                                        # Descargar la banda
                                        file_name = os.path.join(scene_dir, f"{scene_info['id']}_SR_{band}.TIF")
                                        
                                        msg = f"Descargando: {os.path.basename(file_name)}"
                                        print(msg)
                                        yield msg
                                        
                                        with session.get(sr_url, stream=True) as response:
                                            response.raise_for_status()
                                            with open(file_name, 'wb') as file:
                                                for chunk in response.iter_content(chunk_size=8192):
                                                    file.write(chunk)
                                        
                                        print(f"Descargado: {file_name}")
                                        downloaded_band_info[band] = True
                                except Exception as e:
                                    print(f"Error descargando URL construida: {str(e)}")
            
            # Descargar metadatos para todas las escenas
            download_metadata(session, target_feature, scene_dir)
        
        # Verificar si se descargaron todas las bandas necesarias
        missing_bands = [f"{band} ({coll})" for band, coll in required_bands.items() if not downloaded_band_info[band]]
        
        if not missing_bands:
            msg = f"Se descargaron todas las bandas requeridas para el grupo Path={path}, Row={row}, Fecha={date}"
            print(msg)
            yield msg
        else:
            msg = f"Advertencia: No se pudieron descargar las bandas: {', '.join(missing_bands)}"
            print(msg)
            yield msg
    
    yield "\nProceso de descarga finalizado."
    return download_path