import rasterio
import numpy as np
import os
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, LinearSegmentedColormap, ListedColormap
import json
import json
from pathlib import Path
import glob

def read_band(file_path):
    """
    Lee una banda desde un archivo .tif y la devuelve como array numpy.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"El archivo {file_path} no existe")
    
    try:
        with rasterio.open(file_path) as dataset:
            # Leer los datos y guardar el profile para usarlo después
            data = dataset.read(1).astype(np.float32)
            return data
    except Exception as e:
        raise IOError(f"Error al leer el archivo {file_path}: {str(e)}")

def get_required_bands_for_index(index_name):
    """
    Devuelve las bandas necesarias para calcular un índice determinado.
    """
    index_requirements = {
        "NDVI": {"B4": "sr", "B5": "sr"},      # Rojo, NIR
        "NDWI": {"B3": "sr", "B5": "sr"},      # Verde, NIR
        "NDSI": {"B3": "sr", "B6": "sr"},      # Verde, SWIR
        "BSI": {"B2": "sr", "B4": "sr", "B5": "sr", "B6": "sr"},  # Azul, Rojo, NIR, SWIR1
        "LST": {"B10": "st"}  # Térmico
    }
    
    # Devuelve un diccionario que mapea bandas a colecciones
    return index_requirements.get(index_name, {})

def find_metadata_files(base_path):
    """
    Busca archivos de metadatos MTL.json en la ruta dada y sus subdirectorios.
    """
    metadata_files = {
        "sr": [],
        "st": []
    }
    
    # Buscar en la ruta base y todas las subcarpetas
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith("MTL.json"):
                file_path = os.path.join(root, file)
                
                # Determinar si es SR o ST
                if "_SR_" in file or "_sr_" in file.lower():
                    metadata_files["sr"].append(file_path)
                elif "_ST_" in file or "_st_" in file.lower():
                    metadata_files["st"].append(file_path)
                else:
                    # Si no está claro, intentar inferir de la ruta
                    if "sr" in file_path.lower() and "st" not in file_path.lower():
                        metadata_files["sr"].append(file_path)
                    elif "st" in file_path.lower():
                        metadata_files["st"].append(file_path)
    
    return metadata_files

def load_thermal_constants(metadata_files):
    """
    Carga las constantes térmicas desde un archivo de metadatos ST.
    """
    # Valores por defecto en caso de error
    constants = {
        "K1": 774.8853,  # K1 para Landsat 8/9 banda 10
        "K2": 1321.0789,  # K2 para Landsat 8/9 banda 10
        "ML": 0.0003342,  # Multiplicador radiancia
        "AL": 0.1,         # Aditivo radiancia
    }
    
    if not metadata_files.get("st"):
        print("No se encontraron archivos de metadatos ST. Usando valores por defecto.")
        return constants
    
    # Intentar cargar desde cada archivo hasta encontrar uno válido
    for metadata_file in metadata_files["st"]:
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            # Extraer coeficientes de calibración para banda térmica
            if "LANDSAT_METADATA_FILE" in metadata:
                if "LEVEL2_SURFACE_TEMPERATURE_PARAMETERS" in metadata["LANDSAT_METADATA_FILE"]:
                    thermal_constants = metadata["LANDSAT_METADATA_FILE"]["LEVEL2_SURFACE_TEMPERATURE_PARAMETERS"]
                    constants["K1"] = float(thermal_constants["K1_CONSTANT_BAND_10"])
                    constants["K2"] = float(thermal_constants["K2_CONSTANT_BAND_10"])
                
                if "LEVEL1_RADIOMETRIC_RESCALING" in metadata["LANDSAT_METADATA_FILE"]:
                    calib = metadata["LANDSAT_METADATA_FILE"]["LEVEL1_RADIOMETRIC_RESCALING"]
                    constants["ML"] = float(calib["RADIANCE_MULT_BAND_10"])
                    constants["AL"] = float(calib["RADIANCE_ADD_BAND_10"])
                
                print(f"Constantes térmicas cargadas de {os.path.basename(metadata_file)}")
                return constants
        except Exception as e:
            print(f"Error al cargar constantes de {metadata_file}: {e}")
    
    print("No se pudieron cargar constantes térmicas de los archivos. Usando valores por defecto.")
    return constants

def find_band_files(clips_path, band_code, collection=None):
    """
    Busca archivos de bandas según el código de banda y la colección.
    Devuelve el primer archivo encontrado o None si no encuentra ninguno.
    """
    # Patrones de búsqueda
    patterns = [
        f"clip_{band_code}.tif",  # Patrón normal
        f"clip_{band_code}_*.tif",  # Con sufijo
        f"*{band_code}.tif",  # Cualquier prefijo
        f"*{band_code}_*.tif"  # Cualquier combinación
    ]
    
    # Si se especifica colección, añadir patrones específicos
    if collection:
        collection_suffix = collection.upper()
        patterns.extend([
            f"clip_{band_code}_{collection_suffix}.tif",
            f"*{band_code}_{collection_suffix}.tif"
        ])
    
    # Buscar archivos que coincidan con los patrones
    for pattern in patterns:
        matching_files = glob.glob(os.path.join(clips_path, pattern))
        if matching_files:
            return matching_files[0]
    
    # Si llegamos aquí, no se encontró ningún archivo
    return None

def process_indices_from_cutouts(clips_path, output_path, selected_indices):
    """
    Procesa los índices a partir de recortes generados previamente.
    """
    print("\n==== CALCULANDO ÍNDICES A PARTIR DE RECORTES ====")
    # Crear directorio para resultados si no existe
    os.makedirs(output_path, exist_ok=True) 
    
    # Intentar cargar la máscara del área de interés
    mask_file = os.path.join(clips_path, "aoi_mask.tif")
    if os.path.exists(mask_file):
        print(f"Se encontró máscara del área de interés: {mask_file}")
        try:
            with rasterio.open(mask_file) as src:
                mask_data = src.read(1)
                # Convertir a booleano (True donde valor es > 0)
                area_mask = mask_data > 0
                print(f"Máscara cargada: {np.sum(area_mask)} píxeles en el área de interés")
        except Exception as e:
            print(f"Error al cargar máscara: {str(e)}")
            area_mask = None
    else:
        print("No se encontró máscara del área de interés. Se procesará toda la imagen.")
        area_mask = None
    
    # Buscar archivos de metadatos
    download_path = Path(clips_path).parent.parent / "downloads"
    metadata_files = find_metadata_files(download_path)
    thermal_constants = load_thermal_constants(metadata_files)
    
    print(f"Constantes térmicas: K1={thermal_constants['K1']}, K2={thermal_constants['K2']}")
    
    # Verificar qué índices podemos calcular
    calculable_indices = []
    missing_bands_info = {}
    
    for index in selected_indices:
        required_bands = get_required_bands_for_index(index)
        missing_bands = []
        
        # Verificar cada banda requerida
        for band, collection in required_bands.items():
            band_file = find_band_files(clips_path, band, collection)
            if not band_file:
                missing_bands.append(f"{band} ({collection})")
        
        if not missing_bands:
            calculable_indices.append(index)
        else:
            missing_bands_info[index] = missing_bands
    
    if not calculable_indices:
        print("No se pueden calcular los índices solicitados debido a bandas faltantes:")
        for index, missing in missing_bands_info.items():
            print(f" - {index}: Faltan bandas {', '.join(missing)}")
        return {}
    
    print(f"Índices a calcular: {', '.join(calculable_indices)}")
    
    # Preparar estructura para los resultados
    output_files = {}
    
    # Procesar cada índice
    for index in calculable_indices:
        try:
            print(f"\nCalculando índice {index}...")
            
            # Configurar rutas de salida para este índice
            tiff_path = os.path.join(output_path, f"{index}.tif")
            png_path = os.path.join(output_path, f"{index}.png")
            output_files[index] = {'tiff': tiff_path, 'png': png_path}
            
            # Determinar las bandas necesarias
            required_bands = get_required_bands_for_index(index)
            
            # Cargar las bandas
            band_data = {}
            band_profile = None
            
            for band, collection in required_bands.items():
                band_file = find_band_files(clips_path, band, collection)
                if band_file:
                    print(f"Cargando banda {band} desde {os.path.basename(band_file)}...")
                    band_data[band] = read_band(band_file)
                    
                    # Guardar el profile de la primera banda para usarlo al guardar el resultado
                    if band_profile is None:
                        with rasterio.open(band_file) as src:
                            band_profile = src.profile.copy()
                else:
                    print(f"Error: No se encontró archivo para la banda {band} ({collection})")
            
            # Verificar que se cargaron todas las bandas
            if len(band_data) != len(required_bands):
                print(f"Error: No se pudieron cargar todas las bandas para {index}")
                continue
            
            # Calcular el índice según su tipo
            if index == "NDVI":
                red_data = band_data["B4"]
                nir_data = band_data["B5"]
                
                epsilon = 1e-10
                index_data = (nir_data - red_data) / (nir_data + red_data)
                
                # Aplicar la máscara si existe
                if area_mask is not None:
                    # Asegurarse que las dimensiones coincidan
                    if area_mask.shape == index_data.shape:
                        # Establecer como NaN los valores fuera del área de interés
                        index_data = np.where(area_mask, index_data, np.nan)
                    else:
                        print(f"Advertencia: Las dimensiones de la máscara ({area_mask.shape}) no coinciden con el índice ({index_data.shape})")
                
                ndvi_colors = [
                    '#d73027',  # Rojo: muy poca vegetación (-0.5)
                    '#fdae61',  # Naranja claro: vegetación muy escasa (0.0)
                    '#fee08b',  # Amarillo: vegetación escasa (0.2)
                    '#a6d96a',  # Verde claro: vegetación moderada (0.5)
                    '#66bd63',  # Verde: vegetación moderada-alta (0.6)
                    '#1a9850',  # Verde intenso: vegetación densa (0.8)
                    '#006837'   # Verde oscuro: vegetación muy densa (1.0)
                ]
                cmap_name = LinearSegmentedColormap.from_list('ndvi_custom',ndvi_colors )
                
                
                # Rango absoluto para NDVI
                vmin, vmax = -0.1, 1
                title = "Índice de Vegetación de Diferencia Normalizada (NDVI)"
                description = "(-1.0: Sin vegetación | +1.0: Vegetación densa)"
                
            elif index == "NDWI":
                green_data = band_data["B3"]
                nir_data = band_data["B5"]
                
                epsilon = 1e-10
                index_data = (green_data - nir_data) / (green_data + nir_data + epsilon)
                
                # Aplicar la máscara si existe
                if area_mask is not None:
                    # Asegurarse que las dimensiones coincidan
                    if area_mask.shape == index_data.shape:
                        # Establecer como NaN los valores fuera del área de interés
                        index_data = np.where(area_mask, index_data, np.nan)
                    else:
                        print(f"Advertencia: Las dimensiones de la máscara ({area_mask.shape}) no coinciden con el índice ({index_data.shape})")
                
                cmap_name = "Greys_r"  # Azules
                vmin, vmax = -1.0, 0.4
                title = "Índice de Agua de Diferencia Normalizada (NDWI)"
                
            elif index == "NDSI":
                green_data = band_data["B3"]
                swir_data = band_data["B6"]
                
                epsilon = 1e-10
                index_data = (green_data - swir_data) / (green_data + swir_data + epsilon)
                
                # Aplicar la máscara si existe
                if area_mask is not None:
                    # Asegurarse que las dimensiones coincidan
                    if area_mask.shape == index_data.shape:
                        # Establecer como NaN los valores fuera del área de interés
                        index_data = np.where(area_mask, index_data, np.nan)
                    else:
                        print(f"Advertencia: Las dimensiones de la máscara ({area_mask.shape}) no coinciden con el índice ({index_data.shape})")
                
                cmap_name = "Greys_r"  # Azules invertido
                vmin, vmax = -1, 1.0
                title = "Índice de Nieve de Diferencia Normalizada (NDSI)"
                
            elif index == "BSI":
                blue_data = band_data["B2"]
                red_data = band_data["B4"]
                nir_data = band_data["B5"]
                swir_data = band_data["B6"]
                
                epsilon = 1e-10
                num = (swir_data + red_data) - (nir_data + blue_data)
                den = (swir_data + red_data) + (nir_data + blue_data) + epsilon
                index_data = num / den
                
                # Aplicar la máscara si existe
                if area_mask is not None:
                    # Asegurarse que las dimensiones coincidan
                    if area_mask.shape == index_data.shape:
                        # Establecer como NaN los valores fuera del área de interés
                        index_data = np.where(area_mask, index_data, np.nan)
                    else:
                        print(f"Advertencia: Las dimensiones de la máscara ({area_mask.shape}) no coinciden con el índice ({index_data.shape})")
                
                # CAMBIO 1: Paleta de colores más contrastante
                cmap_name = "RdYlGn_r"  # Rojo-Amarillo-Verde invertido (verde para vegetación, rojo para suelo desnudo)
                
                # CAMBIO 7: Ajustar la escala de valores basado en los percentiles de los datos
                # Esto enfatiza mejor las diferencias significativas
                vmin, vmax = -0.10, 0.10  # Valores absolutos fijos para BSI
                print(f"BSI - Rango fijo: vmin={vmin:.2f}, vmax={vmax:.2f}")
                
                title = "Índice de Suelo Desnudo (BSI)"
                
                # Añadir una descripción de la escala de BSI a la visualización
                description = "Valores negativos: Vegetación | Valores cercanos a 0: Mixto | Valores positivos: Suelo desnudo"
                
                # CAMBIO 8: Crear una versión categorizada para visualización alternativa
                png_path_categorized = os.path.join(output_path, f"{index}_categorizado.png")
                
                # Crear categorías para BSI (estos umbrales pueden ajustarse según las características del área)
                """categories = [
                    (-1.0, -0.3, "Vegetación densa", "darkgreen"),
                    (-0.3, -0.1, "Vegetación moderada", "green"),
                    (-0.1, 0.1, "Vegetación dispersa/Mixto", "yellowgreen"),
                    (0.1, 0.3, "Suelo parcialmente expuesto", "orange"),
                    (0.3, 1.0, "Suelo altamente expuesto", "darkred")
                ]
                
                """
                
            elif index == "LST":
                # Cargar la banda térmica (B10)
                thermal_data = band_data["B10"]
                
                # Imprimir información de diagnóstico
                print(f"Banda térmica - Tipo de datos: {thermal_data.dtype}")
                print(f"Banda térmica - Valores: min={np.min(thermal_data)}, max={np.max(thermal_data)}, media={np.mean(thermal_data)}")
                
                
                print("Aplicando conversión estándar para Landsat 8 Collection 2 Level-2 ST")
                # Factor de escala y offset de la documentación del USGS
                scale_factor = 0.00341802
                add_offset = 149.0
                    
                # Convertir a temperatura en Kelvin
                kelvin_temp = thermal_data * scale_factor + add_offset
                print(f"Temperatura en Kelvin: min={np.min(kelvin_temp)}, max={np.max(kelvin_temp)}, media={np.mean(kelvin_temp)}")
                    
                # Convertir a Celsius
                index_data = kelvin_temp - 273.15
                
                print(f"Temperatura final en Celsius: min={np.min(index_data)}, max={np.max(index_data)}, media={np.mean(index_data)}")
                
                index_data = np.clip(index_data, 0, 50)
                
                # Aplicar la máscara si existe
                if area_mask is not None:
                    if area_mask.shape == index_data.shape:
                        index_data = np.where(area_mask, index_data, np.nan)
                    else:
                        print(f"Advertencia: Las dimensiones de la máscara ({area_mask.shape}) no coinciden con el índice ({index_data.shape})")
                
                # Configuración de visualización
                cmap_name = "jet"
                vmin, vmax = 12, 40
                title = "Temperatura de Superficie (LST)"
                
            else:
                print(f"Índice {index} no implementado")
                continue
            
            # Actualizar el perfil para 32 bits
            band_profile.update(dtype=rasterio.float32)
            
            # Guardar el índice como archivo GeoTIFF
            with rasterio.open(tiff_path, 'w', **band_profile) as dst:
                # Reemplazar NaN con nodata
                result_data_clean = np.where(np.isnan(index_data), -9999, index_data)
                dst.write(result_data_clean.astype(np.float32), 1)
            
            print(f"Índice {index} guardado en {tiff_path}")
            
            # Generar visualización del índice
            print(f"Generando visualización para {index}...")
            plt.figure(figsize=(12, 8))
            
            # Enmascarar valores nodata o NaN
            masked_data = np.ma.masked_where(
                (np.isnan(index_data)) | (index_data == -9999), 
                index_data
            )
            
            # Crear visualización con escala de colores apropiada
            plt.imshow(masked_data, cmap=plt.get_cmap(cmap_name), norm=Normalize(vmin=vmin, vmax=vmax))
            plt.colorbar(label=index)
            plt.title(title)
            
            # Guardar como imagen PNG
            plt.savefig(png_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"Visualización guardada en {png_path}")
            
            # Calcular estadísticas básicas
            valid_data = index_data[~np.isnan(index_data)]
            stats = {
                'min': float(np.min(valid_data)) if len(valid_data) > 0 else None,
                'max': float(np.max(valid_data)) if len(valid_data) > 0 else None,
                'mean': float(np.mean(valid_data)) if len(valid_data) > 0 else None,
                'std': float(np.std(valid_data)) if len(valid_data) > 0 else None
            }
            
            # Añadir información de estadísticas a la salida
            output_files[index].update(stats)
            
        except Exception as e:
            import traceback
            print(f"Error al calcular índice {index}: {str(e)}")
            print(traceback.format_exc())
    
    # Guardar un registro de los índices procesados
    if output_files:
        registro_path = os.path.join(output_path, "registro_indices.json")
        with open(registro_path, 'w') as f:
            json.dump(output_files, f, indent=4)
        print(f"\nRegistro de índices guardado en {registro_path}")
    
    return output_files

def process_indices_from_cutouts_wrapper(selected_indices):
    """
    Función envoltorio para procesar índices desde recortes.
    """

    # Ruta basada en la ubicación del script
    script_dir = Path(__file__).parent  # Carpeta donde está el script
    clips_path = script_dir.parent.parent / "data" / "temp" / "processed" / "clip"

    try:
        # Verificar que la ruta de recortes existe
        if not os.path.exists(clips_path):
            print(f"Error: La ruta de recortes {clips_path} no existe")
            return False
            
        # Verificar que hay índices seleccionados
        if not selected_indices or len(selected_indices) == 0:
            print("Error: No hay índices seleccionados para calcular")
            return False
        
        msg = f"Índices seleccionados para calcular: {', '.join(selected_indices)}"
        print(msg)
        yield msg
        
        # Crear directorio para salida    
        output_path = script_dir.parent.parent / "data" / "exports" / "indices"
        os.makedirs(output_path, exist_ok=True)
        
        # Llamar a la función principal con manejo de errores
        try:
            results = process_indices_from_cutouts(clips_path, output_path, selected_indices)
        except Exception as e:
            raise Exception(f"Error al procesar índices: {str(e)}")
        
        # Verificar resultados
        if not results:
            raise Exception("No se pudieron calcular los índices solicitados.")
        
        # Mostrar resumen de los índices calculados
        print("\n==== RESUMEN DE ÍNDICES CALCULADOS ====")
        for index, info in results.items():
            stats_str = ""
            if 'min' in info and info['min'] is not None:
                stats_str = f"Min={info['min']:.2f}, Max={info['max']:.2f}, Media={info['mean']:.2f}"
            
            print(f"{index}: {os.path.basename(info['tiff'])} → {os.path.basename(info['png'])} {stats_str}")
        
        return True
    
    except Exception as e:
        raise Exception(f"Error al procesar índices: {str(e)}")