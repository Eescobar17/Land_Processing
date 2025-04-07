import rasterio
import numpy as np
import os
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import json
from pathlib import Path

def read_band(file_path):
    """
    Lee una banda desde un archivo .tif y la devuelve como array numpy.
    
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"El archivo {file_path} no existe")
    
    try:
        with rasterio.open(file_path) as dataset:
            return dataset.read(1).astype(np.float32)
    except Exception as e:
        raise IOError(f"Error al leer el archivo {file_path}: {str(e)}")

def get_required_bands_for_index(index_name):
    """
    Devuelve las bandas necesarias para calcular un índice determinado.
    """
    index_requirements = {
        "NDVI": ["B4", "B5"],      # Rojo, NIR
        "NDWI": ["B3", "B5"],      # Verde, NIR
        "NDSI": ["B3", "B6"],      # Verde, SWIR
        "BSI": ["B2", "B4", "B5", "B6"],  # Azul, Rojo, NIR, SWIR1
        "LST": ["B10"]             # Térmico
    }
    
    # Siempre devolver una lista (incluso vacía) para evitar el error NoneType
    return index_requirements.get(index_name, [])

def process_indices_from_cutouts(clips_path, output_path, selected_indices):
    """
    Procesa los índices a partir de recortes generados previamente.
    
    """
    print("\n==== CALCULANDO ÍNDICES A PARTIR DE RECORTES ====")
    # Crear directorio para resultados si no existe
    os.makedirs(output_path, exist_ok=True) 
    # Buscar recortes disponibles
    print("Buscando recortes disponibles...")
    clips = {}
    for file in os.listdir(clips_path):
        if file.startswith("clip_B") and file.endswith(".tif"):
            band = file.replace("clip_", "").replace(".tif", "")
            clips[band] = os.path.join(clips_path, file)
    if not clips:
        raise Exception("No se encontraron archivos de recortes en", clips_path) 
    print(f"Recortes encontrados: {', '.join(clips.keys())}")
    # Verificar qué índices podemos calcular con las bandas disponibles
    calculable_indices = []
    non_calculable_indices = {}
    
    for index in selected_indices:
        required_bands = get_required_bands_for_index(index)
        
        # Verificar qué bandas faltan
        missing_bands = [band for band in required_bands if band not in clips]
        
        if not missing_bands:
            calculable_indices.append(index)
        else:
            non_calculable_indices[index] = missing_bands
    
    if not calculable_indices:
        print("No se pueden calcular los índices solicitados debido a bandas faltantes:")
        for indice, faltantes in non_calculable_indices.items():
            print(f" - {index}: Faltan bandas {', '.join(faltantes)}")
        return {}
    
    print(f"Índices a calcular: {', '.join(calculable_indices)}")
    
    # Preparar estructura para los resultados
    output_files = {}
    
    # Cargar todas las bandas necesarias de una sola vez
    bands = {}
    for band_code in clips.keys():
        try:
            print(f"Cargando banda {band_code}...")
            bands[band_code] = read_band(clips[band_code])
            print(f" - {band_code}: OK")
        except Exception as e:
            print(f" - {band_code}: ERROR - {str(e)}")
    
    # Procesar cada índice
    for index in calculable_indices:
        try:
            print(f"\nCalculando índice {index}...")
            
            # Configurar rutas de salida para este índice
            tiff_path = os.path.join(output_path, f"{index}.tif")
            png_path = os.path.join(output_path, f"{index}.png")
            output_files[index] = {'tiff': tiff_path, 'png': png_path}
            
            # Calcular el índice según su tipo
            if index == "NDVI":
                # Verificar que tenemos las bandas necesarias
                if "B4" in bands and "B5" in bands:
                    red_data = bands["B4"]
                    nir_data = bands["B5"]
                    
                    epsilon = 1e-10
                    index_data = (nir_data - red_data) / (nir_data + red_data + epsilon)
                    
                    cmap_name = "RdYlGn"  # Rojo-Amarillo-Verde
                    vmin, vmax = -1.0, 1.0
                    title = "Índice de Vegetación de Diferencia Normalizada (NDVI)"
                else:
                    print(f"Error: Faltan bandas necesarias para NDVI")
                    continue
                
            elif index == "NDWI":
                if "B3" in bands and "B5" in bands:
                    green_data = bands["B3"]
                    nir_data = bands["B5"]
                    
                    epsilon = 1e-10
                    index_data = (green_data - nir_data) / (green_data + nir_data + epsilon)
                    
                    cmap_name = "Blues"  # Azules
                    vmin, vmax = -1.0, 1.0
                    title = "Índice de Agua de Diferencia Normalizada (NDWI)"
                else:
                    print(f"Error: Faltan bandas necesarias para NDWI")
                    continue
                
            elif index == "NDSI":
                if "B3" in bands and "B6" in bands:
                    green_data = bands["B3"]
                    swir_data = bands["B6"]
                    
                    epsilon = 1e-10
                    index_data = (green_data - swir_data) / (green_data + swir_data + epsilon)
                    
                    cmap_name = "Blues_r"  # Azules invertido
                    vmin, vmax = -1.0, 1.0
                    title = "Índice de Nieve de Diferencia Normalizada (NDSI)"
                else:
                    print(f"Error: Faltan bandas necesarias para NDSI")
                    continue
                
            elif index == "BSI":
                if "B2" in bands and "B4" in bands and "B5" in bands and "B6" in bands:
                    blue_data = bands["B2"]
                    red_data = bands["B4"]
                    nir_data = bands["B5"]
                    swir_data = bands["B6"]
                    
                    epsilon = 1e-10
                    num = (swir_data + red_data) - (nir_data + blue_data)
                    den = (swir_data + red_data) + (nir_data + blue_data) + epsilon
                    index_data = num / den
                    
                    cmap_name = "YlOrBr"  # Amarillo-Naranja-Marrón
                    vmin, vmax = -1.0, 1.0
                    title = "Índice de Suelo Desnudo (BSI)"
                else:
                    print(f"Error: Faltan bandas necesarias para BSI")
                    continue
                
            elif index == "LST":
                if "B10" in bands:
                    thermal_data = bands["B10"]
                    
                    # Constantes para Landsat 8/9
                    K1 = 774.8853
                    K2 = 1321.0789
                    
                    # Convertir los números digitales a radiancia (aproximación)
                    radiance = thermal_data * 0.1
                    
                    # Calcular temperatura en Kelvin a partir de radiancia
                    epsilon = 0.95  # Emisividad (aproximada)
                    index_data = K2 / (np.log((K1 / (radiance + 1e-10)) + 1))
                    
                    # Convertir de Kelvin a Celsius
                    index_data = index_data - 273.15
                    
                    cmap_name = "jet"  # Jet (azul-cian-amarillo-rojo)
                    vmin, vmax = 0, 50  # Celsius
                    title = "Temperatura de Superficie (LST)"
                else:
                    print(f"Error: Faltan bandas necesarias para LST")
                    continue
                
            else:
                print(f"Índice {index} no implementado")
                continue
            
            # Obtener el perfil (metadatos geoespaciales) de una de las bandas originales
            profile = None
            for band_code in get_required_bands_for_index(index):
                try:
                    with rasterio.open(clips[band_code]) as src:
                        profile = src.profile.copy()
                        profile.update(dtype=rasterio.float32)
                    break
                except Exception as e:
                    continue
            
            if not profile:
                print(f"Error: No se pudo obtener el perfil de metadatos para {index}")
                continue
            
            # Guardar el índice como archivo GeoTIFF
            with rasterio.open(tiff_path, 'w', **profile) as dst:
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

