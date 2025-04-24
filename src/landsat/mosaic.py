import os
import glob
import json
from rasterio.mask import mask
import geopandas as gpd
from osgeo import gdal
from pathlib import Path
import subprocess
import rasterio
from shapely.geometry import mapping, box
import traceback
import re
import numpy as np
import shutil
gdal.UseExceptions()

def extract_mosaic_by_polygon(mosaic_path, polygon_path, output_path):
    """
    Recorta un mosaico de banda utilizando un polígono con manejo de diferentes CRS.
    También crea una máscara binaria que indica el área de interés dentro del recorte.
    """
    try:
        print(f"Recortando mosaico {os.path.basename(mosaic_path)} con polígono...")
        # Crear directorio para recortes si no existe
        os.makedirs(output_path, exist_ok=True)
        # Ruta del archivo de salida
        band_name = os.path.basename(mosaic_path).replace("mosaic_", "").replace(".tif", "")
        output_file = os.path.join(output_path, f"clip_{band_name}.tif")
        mask_file = os.path.join(output_path, f"aoi_mask.tif")
        
        # Abrir el mosaico para obtener su CRS y extensión
        with rasterio.open(mosaic_path) as src:
            raster_crs = src.crs
            raster_bounds = src.bounds
            raster_bbox = box(raster_bounds.left, raster_bounds.bottom, 
                             raster_bounds.right, raster_bounds.top)
            
            print(f"CRS del raster: {raster_crs}")
            print(f"Extensión del raster: {raster_bounds}")
        
        # Cargar el polígono desde el archivo
        poligono_gdf = gpd.read_file(polygon_path)
        poligono_crs = poligono_gdf.crs
        
        is_path_row_mode = False
        try:
            if poligono_gdf.empty or poligono_gdf.geometry.is_empty.all():
                is_path_row_mode = True
            else:
                # Verificar si el archivo es del tipo "source_file" (generado) o no
                polygon_filename = os.path.basename(polygon_path)
                if not polygon_filename.startswith("source_file"):
                    is_path_row_mode = True
        except:
            is_path_row_mode = True
        
        if is_path_row_mode:
            print("Detectado modo path/row: Copiando el mosaico completo sin recortar")
            # Simplemente copiar el archivo original
            shutil.copy(mosaic_path, output_file)
            
            # Crear una máscara que cubra toda el área
            with rasterio.open(mosaic_path) as src:
                mask_array = np.ones((src.height, src.width), dtype=np.uint8)
                mask_meta = src.meta.copy()
                mask_meta.update({
                    "count": 1,
                    "dtype": "uint8",
                    "nodata": 0
                })
                
                with rasterio.open(mask_file, "w", **mask_meta) as dest:
                    dest.write(mask_array, 1)
            
            print(f"Recorte para banda {band_name} creado en {output_file}")
            print(f"Máscara para el área completa creada en {mask_file}")
            return output_file
        
        
        
        
        print(f"CRS del polígono: {poligono_crs}")
        print(f"Extensión del polígono: {poligono_gdf.total_bounds}")
        
        # Verificar si los CRS son diferentes y reproyectar si es necesario
        if poligono_crs != raster_crs:
            print(f"Reproyectando polígono de {poligono_crs} a {raster_crs}")
            poligono_gdf = poligono_gdf.to_crs(raster_crs)
        
        # Verificar intersección espacial antes de intentar recortar
        intersects = False
        for geom in poligono_gdf.geometry:
            if geom.intersects(raster_bbox):
                intersects = True
                break
        
        if not intersects:
            print("ERROR: El polígono no intersecta con el raster.")
            print("Utilizando el área completa del raster como alternativa...")
            
            # Usar el bbox del raster como geometría de recorte
            geometries = [mapping(raster_bbox)]
            
            # Crear una copia del raster original sin recortar
            output_file = os.path.join(output_path, f"clip_{band_name}.tif")
            shutil.copy(mosaic_path, output_file)
            
            # Crear una máscara que cubra todo el raster (todos los píxeles válidos)
            with rasterio.open(mosaic_path) as src:
                mask_array = np.ones((src.height, src.width), dtype=np.uint8)
                mask_meta = src.meta.copy()
                mask_meta.update({
                    "count": 1,
                    "dtype": "uint8",
                    "nodata": 0
                })
                
                mask_file = os.path.join(output_path, f"aoi_mask.tif")
                with rasterio.open(mask_file, "w", **mask_meta) as dest:
                    dest.write(mask_array, 1)
            
            print(f"Recorte completo para banda {band_name} creado en {output_file}")
            print(f"Máscara para el área completa creada en {mask_file}")
            return output_file
        else:
            print("El polígono intersecta con el raster. Procediendo con el recorte normal.")
            geometries = [mapping(geom) for geom in poligono_gdf.geometry]
        
        # Abrir el mosaico y realizar el recorte
        with rasterio.open(mosaic_path) as src:
            # Realizar el recorte
            out_image, out_transform = mask(src, geometries, crop=True, all_touched=True)
            # Actualizar metadatos
            out_meta = src.meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
                "compress": "deflate",
                "predictor": 2,
                "tiled": True
            })
            
            # Guardar el resultado
            with rasterio.open(output_file, "w", **out_meta) as dest:
                dest.write(out_image)
            
            # NUEVO: Crear una máscara binaria del área del polígono
            # Inicializar una máscara con ceros (fuera del área)
            mask_array = np.zeros((out_image.shape[1], out_image.shape[2]), dtype=np.uint8)
            
            # Rasterizar el polígono sobre la máscara
            from rasterio import features
            
            # Crear una ventana de transformación ajustada al recorte
            for geom in poligono_gdf.geometry:
                # Rasterizar cada geometría como 1 en la máscara
                features.rasterize(
                    [(geom, 1)],
                    out=mask_array,
                    transform=out_transform,
                    all_touched=True
                )
            
            # Guardar la máscara como GeoTIFF
            mask_meta = out_meta.copy()
            mask_meta.update({
                "count": 1,
                "dtype": "uint8",
                "nodata": 0
            })
            
            with rasterio.open(mask_file, "w", **mask_meta) as dest:
                dest.write(mask_array, 1)
            
            print(f"Máscara del área de interés creada en {mask_file}")
        
        # Verificar que el archivo se haya creado correctamente
        if os.path.exists(output_file) and os.path.exists(mask_file):
            print(f"Recorte para banda {band_name} creado en {output_file}")
            print(f"Máscara para el área de interés creada en {mask_file}")
            return output_file
        else:
            print(f"Error: No se pudieron crear los archivos de salida")
            return None
            
    except Exception as e:
        print(f"Error al recortar mosaico {mosaic_path}: {str(e)}")
        print(traceback.format_exc())
        return None

def build_mosaic_per_band(band_files, output_path, band_name, temp_dir=None):
    """
    Crea un mosaico para una banda específica, priorizando escenas con menor nubosidad.
    """
    # Crear directorio para mosaicos si no existe
    os.makedirs(output_path, exist_ok=True)
    
    # Crear directorio temporal si es necesario
    if temp_dir is None:
        temp_dir = os.path.join(output_path, "temp")

    os.makedirs(temp_dir, exist_ok=True)
    # Ordenar archivos por nubosidad (menor a mayor)
    sorted_files = sorted(band_files, key=lambda x: x[1])
    # Ruta del mosaico final
    output_mosaic = os.path.join(output_path, f"mosaic_{band_name}.tif")
    
    # Enfoque usando GDAL directamente (más control sobre el proceso)
    # Crear un archivo VRT para el mosaico
    vrt_path = os.path.join(temp_dir, f"mosaic_{band_name}.vrt")
    
    # Crear un archivo de texto con la lista de archivos ordenados por nubosidad
    list_file = os.path.join(temp_dir, f"filelist_{band_name}.txt")
    with open(list_file, 'w') as f:
        for file, _ in sorted_files:
            f.write(file + '\n')
    
    # Construir el comando para crear el VRT
    gdal_build_vrt_cmd = [
        'gdalbuildvrt',
        '-allow_projection_difference',
        '-resolution', 'highest',
        '-input_file_list', list_file,
        vrt_path
    ]
    
    # Ejecutar el comando
    cmd = ' '.join(gdal_build_vrt_cmd)
    print(f"Ejecutando: {cmd}")

    try:
        gdal.BuildVRT(
            vrt_path, 
            [archivo for archivo, _ in sorted_files],
            options=gdal.BuildVRTOptions(
                resolution='highest',
                separate=False,
                allowProjectionDifference=True
            )
        )
    except Exception as e:
        print(f"Error al crear VRT: {str(e)}")
        subprocess.run(cmd, shell=True, check=True) # Ejecutar como proceso externo si falla la API

    # Convertir el VRT al mosaico GeoTIFF final
    gdal_translate_cmd = [
        'gdal_translate',
        '-co', 'COMPRESS=DEFLATE',
        '-co', 'PREDICTOR=2',
        '-co', 'TILED=YES',
        vrt_path,
        output_mosaic
    ]
    
    cmd = ' '.join(gdal_translate_cmd)
    print(f"Ejecutando: {cmd}")
    
    try:
        gdal.Translate(
            output_mosaic,
            vrt_path,
            options=gdal.TranslateOptions(
                creationOptions=['COMPRESS=DEFLATE', 'PREDICTOR=2', 'TILED=YES']
            )
        )
    except Exception as e:
        print(f"Error al convertir VRT a GeoTIFF: {str(e)}")
        subprocess.run(cmd, shell=True, check=True) # Ejecutar como proceso externo si falla la API
    
    print(f"Mosaico para banda {band_name} creado en {output_mosaic}")
    
    return output_mosaic

def extract_collection_indicator(filename):
    """
    Extrae el indicador de colección (SR o ST) de un nombre de archivo.
    """
    # Patrones de búsqueda para identificar la colección
    sr_patterns = ["_SR_", "_sr_", "sr_"]
    st_patterns = ["_ST_", "_st_", "st_"]
    
    for pattern in sr_patterns:
        if pattern in filename:
            return "SR"
    
    for pattern in st_patterns:
        if pattern in filename:
            return "ST"
    
    # Por defecto, asumimos SR
    return "SR"

def get_cloud_cover(scene_dir):
    """
    Intenta obtener el porcentaje de nubosidad de los metadatos de la escena.
    """
    info_files = glob.glob(os.path.join(scene_dir, "*MTL.json"))
    if info_files:
        try:
            with open(info_files[0], 'r') as info_file:
                info_data = json.load(info_file)
                return float(info_data["LANDSAT_METADATA_FILE"]["IMAGE_ATTRIBUTES"]["CLOUD_COVER"])
        except (KeyError, ValueError, Exception) as e:
            print(f"Error al leer archivo de info: {str(e)}")
            return None
    
    # Si no encontramos la información, lanzar excepción
    raise ValueError(f"No se pudo obtener la nubosidad para {scene_dir}")

def get_scenes_by_band(download_path):
    """
    Busca todas las bandas descargadas y las organiza por tipo de banda,
    diferenciando entre colecciones SR y ST.
    """
    print("Buscando archivos de bandas descargadas...")
    
    sorted_bands = {}
    
    # Buscar todas las carpetas de escenas (asumimos que son subdirectorios del download_path)
    for scene_dir in glob.glob(os.path.join(download_path, "scene_*")):
        try:
            # Intentar obtener desde un archivo de metadatos si existe
            cloud_cover = get_cloud_cover(scene_dir)
        except:
            # Si no hay metadatos, asumimos un valor alto para priorizar otras escenas
            cloud_cover = 100
            print(f"No se pudo determinar la nubosidad para {scene_dir}, asumiendo 100%")
        
        # Buscar todos los archivos TIF en esta carpeta
        for tif_file in glob.glob(os.path.join(scene_dir, "*.TIF")):
            # Determinar a qué banda corresponde el archivo
            filename = os.path.basename(tif_file)
            
            # Extraer el nombre de la banda usando una expresión regular más robusta
            band_match = re.search(r'_B(\d+)\.', filename)
            if band_match:
                band_number = band_match.group(1)
                band = f"B{band_number}"
                
                # Determinar la colección (SR o ST)
                collection = extract_collection_indicator(filename)
                band_key = f"{band}_{collection}"
                
                # Si la banda no está en el diccionario, crear una lista vacía
                if band_key not in sorted_bands:
                    sorted_bands[band_key] = []
                
                # Agregar la ruta del archivo y el porcentaje de nubosidad
                sorted_bands[band_key].append((tif_file, cloud_cover))
    
    # Verificar si encontramos bandas
    if not sorted_bands:
        raise Exception(f"No se encontraron archivos de bandas en {download_path}")
    
    # Mostrar información de las bandas encontradas
    for banda, archivos in sorted_bands.items():
        print(f"Banda {banda}: {len(archivos)} archivos encontrados")
    
    return sorted_bands

def generate_mosaics_and_clips(temp_dir=None):
    """
    Función principal que coordina el proceso completo:
    1. Busca todas las bandas descargadas
    2. Crea mosaicos por banda
    3. Recorta los mosaicos según el polígono
    """
    script_dir = Path(__file__).parent
    data_path = script_dir.parent.parent / "data" / "temp" / "source"
    # Buscar archivos con extensión .geojson y .shp
    files = sorted(
        glob.glob(str(data_path / "*.geojson")) + glob.glob(str(data_path / "*.shp")),
        key=os.path.getmtime,
        reverse=True
    )
    if not files:
        raise Exception(f"No se encontró ningún archivo en: {data_path}")
    polygon_path = files[0]

    if not os.path.exists(polygon_path):
        raise Exception(f"El archivo del polígono {polygon_path} no existe.")

    download_path = script_dir.parent.parent / "data" / "temp" / "downloads"
    try:
        msg = "Obteniendo bandas espectrales descargadas...\n"
        print(msg)
        yield msg
        sorted_bands = get_scenes_by_band(download_path)
    except Exception as e:
        raise str(e)

    if not sorted_bands:
        raise Exception("No se encontraron bandas para procesar")
    processed_mosaics = {}
    output_mosaic = script_dir.parent.parent / "data" / "temp" / "processed" / "mosaic"
    msg = "Creando mosaico para cada banda...\n"
    print(msg)
    yield msg
    for band, files in sorted_bands.items():
        try:
            print(f"\nCreando mosaico para la banda {band}...")
            mosaic_path = build_mosaic_per_band(files, output_mosaic, band, temp_dir)

            if mosaic_path and os.path.exists(mosaic_path):
                processed_mosaics[band] = mosaic_path
                print(f"Mosaico creado exitosamente: {mosaic_path}")
            else:
                raise Exception(f"No se pudo crear el mosaico para la banda {band}")
            
        except Exception as e:
            print(f"Error al crear mosaico para banda {band}: {str(e)}")
            print(traceback.format_exc())
    if not processed_mosaics:
        raise Exception("No se pudo crear ningún mosaico.")

    created_clips = {}
    clips_path = script_dir.parent.parent / "data" / "temp" / "processed" / "clip"

    yield "Mosaico generado. Realizando corte...\n"
    for band, mosaic_path in processed_mosaics.items():
        try:
            print(f"\nRecortando mosaico para banda {band}...")
            clip_path = extract_mosaic_by_polygon(mosaic_path, polygon_path, clips_path)

            if clip_path is not None:
                created_clips[band] = clip_path
                print(f"Recorte creado exitosamente: {clip_path}")
            else:
                raise Exception(f"No se pudo crear el recorte para la banda {band}")
        except Exception as e:
            print(f"Error al recortar mosaico para banda {band}: {str(e)}")
            print(traceback.format_exc())
    results = {
        "mosaicos": processed_mosaics,
        "recortes": created_clips
    }
    output_clips = script_dir.parent.parent / "data" / "exports"
    os.makedirs(output_clips, exist_ok=True)
    log_path = os.path.join(output_clips, "registro_procesamiento.json")

    try:
        with open(log_path, 'w') as f:
            json.dump(results, f, indent=4)
    except Exception as e:
        print(f"Error al guardar el registro de procesamiento: {str(e)}")
        print(traceback.format_exc())

    msg = f"\nProcesamiento completado. Se generaron {len(processed_mosaics)} mosaicos y {len(created_clips)} recortes.\nRegistro guardado en {log_path}"
    print(msg)
    yield msg

    return results