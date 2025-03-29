import os
import requests
from bs4 import BeautifulSoup
from .config import USGS_USERNAME, USGS_PASSWORD
from pathlib import Path

LOGIN_URL = "https://ers.cr.usgs.gov/login"

def login_usgs():
    """Logs into the USGS system and returns an authenticated session."""
    session = requests.Session()
    
    # Get the login page to extract the CSRF token
    response = session.get(LOGIN_URL)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html5lib')
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
   
    required_bands = set()
    
    for index in selected_indices:
        if index == "NDVI":
            required_bands.update(["B4", "B5"])  # Red, NIR
        elif index == "NDWI":
            required_bands.update(["B3", "B5"])  # Green, NIR
        elif index == "NDSI":
            required_bands.update(["B3", "B6"])  # Green, SWIR
        elif index == "BSI":
            required_bands.update(["B2", "B4", "B5", "B6"])  # Blue, Red, NIR, SWIR1
        elif index == "LST":
            required_bands.update(["B10"])  # TIRS1
    
    if required_bands:
        print(f"\nÍndices seleccionados: {', '.join(selected_indices)}")
        print(f"Bandas requeridas: {', '.join(required_bands)}")
    
    return list(required_bands)

def download_selective_bands(feature, required_bands, download_path, session):
    """
    Descarga solo las bandas específicas de una imagen Landsat.
    
    Args:
        feature: Característica (feature) de Landsat
        required_bands: Lista de bandas requeridas (e.g., ["B2", "B4", "B5"])
        download_path: Ruta donde guardar las imágenes descargadas
        session: Sesión iniciada en USGS
    Returns:
        str: Ruta base para los archivos descargados, o None si falló
    """
    
    # Verificar si tiene assets
    if 'assets' not in feature:
        print(f"Error: La imagen {feature.get('id', 'desconocida')} no tiene la clave 'assets'")
        return None
    
    # Obtener ID de la escena
    scene_id = feature.get('id', 'unknown')
    print(f"Descargando bandas {', '.join(required_bands)} para la escena {scene_id}")
    
    # Mostrar los assets disponibles para diagnóstico
    print(f"Assets disponibles: {', '.join(feature['assets'].keys())}")
    
    # Determinar la ruta base para los archivos
    base_path = os.path.join(download_path, scene_id.split('_SR')[0])
    
    # Bandera para verificar si todas las descargas fueron exitosas
    all_successful = True
    downloaded_bands = []
    
    # Intentar diferentes estrategias para encontrar y descargar cada banda
    for band in required_bands:
        band_found = False
        
        # Lista de posibles variantes para cada banda
        band_variants = [
            band,                     # Ejemplo: "B4"
            band.lower(),             # Ejemplo: "b4"
            f"band{band[1:]}",        # Ejemplo: "band4"
            f"band_{band[1:]}",       # Ejemplo: "band_4"
            f"sr_{band.lower()}",     # Ejemplo: "sr_b4"
            f"{band.lower()}"         # Ejemplo: "b4"
        ]
        
        # Buscar la banda en todas sus variantes
        for variant in band_variants:
            if variant in feature['assets'] and 'href' in feature['assets'][variant]:
                download_url = feature['assets'][variant]['href']
                print(f"Encontrada banda {band} como '{variant}'")
                band_found = True
                break
        
        # Si no se encontró por nombre exacto, buscar cualquier asset que contenga el nombre de la banda
        if not band_found:
            for asset_key, asset_info in feature['assets'].items():
                if 'href' in asset_info and band.lower() in asset_key.lower():
                    download_url = asset_info['href']
                    print(f"Encontrada banda {band} en asset '{asset_key}'")
                    band_found = True
                    break
        
        # Si aún no se encuentra, intentar con otros patrones conocidos
        if not band_found:
            # Para Landsat, a veces las bandas están en URLs que siguen patrones específicos
            # Intentar construir la URL basada en otra URL conocida
            base_url = None
            
            # Buscar cualquier URL de asset que podamos usar como base
            for asset_key, asset_info in feature['assets'].items():
                if 'href' in asset_info and asset_info['href'].lower().endswith('.tif'):
                    base_url = asset_info['href']
                    break
            
            if base_url:
                # Intentar deducir el patrón de nombrado
                for pattern in [
                    lambda url, b: url.replace(url.split('_')[-1], f"{b}.TIF"),  # Reemplazar último segmento
                    lambda url, b: url.replace(url.split('_')[-1].split('.')[0], b)  # Reemplazar solo el nombre de banda
                ]:
                    try:
                        test_url = pattern(base_url, band)
                        # Verificar si la URL existe con una solicitud HEAD
                        head_response = session.head(test_url)
                        if head_response.status_code == 200:
                            download_url = test_url
                            print(f"Deducida URL para banda {band}: {download_url}")
                            band_found = True
                            break
                    except:
                        pass
        
        # Si no se pudo encontrar la banda, registrar el error
        if not band_found:
            print(f"Error: No se pudo encontrar la banda {band} en los assets disponibles")
            all_successful = False
            continue
        
        # Crear el nombre del archivo local
        file_name = os.path.join(download_path, f"{scene_id.split('_SR')[0]}_{band}.TIF")
        print(f"Descargando: {os.path.basename(file_name)}")

        try:
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
            
            print(f"Descargado: {file_name}")
            downloaded_bands.append(band)
        except Exception as e:
            print(f"Error al descargar la banda {band}: {str(e)}")
            all_successful = False

        # ------------------
        # Descargar Metadata
        # ------------------

        # Crear el nombre del archivo local
        file_name = os.path.join(download_path, f"{scene_id.split('_SR')[0]}_MTL.json")
        download_url = feature['assets']['MTL.json']['href']
        print(f"Descargando: {os.path.basename(file_name)}")

        try:
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
            
            print(f"Descargado: {file_name}")
        except Exception as e:
            print(f"Error al descargar la metadata")
            all_successful = False
    
    # Verificar que se descargaron todas las bandas requeridas
    if all_successful:
        print(f"Se descargaron todas las bandas requeridas: {', '.join(downloaded_bands)}")
        return base_path
    elif downloaded_bands:
        print(f"Advertencia: Solo se descargaron algunas bandas: {', '.join(downloaded_bands)}")
        print(f"Faltan las bandas: {', '.join(set(required_bands) - set(downloaded_bands))}")
        return base_path  # Devolver la ruta base para las bandas que sí se pudieron descargar
    else:
        print("Error: No se pudo descargar ninguna banda")
        return None

def download_images(features, scenes_needed, required_bands):
    """ Descargar cada escena necesaria con todas las bandas requeridas """

    # Ruta basada en la ubicación del script
    script_dir = Path(__file__).parent  # Carpeta donde está el script
    download_path = script_dir.parent.parent / "data" / "temp" / "downloads"  # Ruta a la carpeta con los archivos
    os.makedirs(download_path, exist_ok=True)

    downloaded_scenes = []

    # Iniciar sesión en USGS
    session = login_usgs()
    
    for i, scene_info in enumerate(scenes_needed):
        # Buscar la característica correspondiente en la lista original
        scene_id = scene_info['id']
        
        target_feature = None
        for feature in features:
            if feature.get('id') == scene_id:
                target_feature = feature
                break

        if target_feature:
            print(f"\nDescargando escena {i+1}/{len(scenes_needed)}: {scene_id}")
            
            # Crear un subdirectorio específico para esta escena
            scene_dir = os.path.join(download_path, f"scene_{scene_info['path']}_{scene_info['row']}")
            os.makedirs(scene_dir, exist_ok=True)
            
            # Descargar todas las bandas requeridas
            base_path = download_selective_bands(target_feature, required_bands, scene_dir, session)
            
            if base_path:
                print(f"Escena {scene_id} descargada correctamente con todas las bandas requeridas")
                downloaded_scenes.append({
                    'scene_dir': scene_dir,
                    'base_path': base_path,
                    'scene_id': scene_id
                })
            else:
                print(f"Error al descargar la escena {scene_id}")
        else:
            print(f"No se encontró la característica correspondiente a {scene_id}")