from ..landsat import (generate_landsat_query, fetch_stac_server, 
                      determine_required_bands, download_images, 
                      process_metadata, process_indices_from_cutouts_wrapper, 
                      extract_mosaic_by_polygon, build_mosaic_per_band, get_scenes_by_band)

import os
import glob
import json
import shutil
from pathlib import Path
import traceback

class LandsatController:
    """Controlador para gestionar la búsqueda y descarga de imágenes Landsat."""
    
    def __init__(self, config):
        self.config = config

    def fetch_data(self):
        """Genera la consulta STAC y la ejecuta para obtener los metadatos."""
        
        # Construcción del query a partir de la configuración
        yield "Generando Query a partir de la información ingresada...\n"
        query = generate_landsat_query(**self.config)
        
        # Obtención de la metadata
        yield "Query generado. Obteniendo metadata...\n"
        features = fetch_stac_server(query)

        # Procesar metadatos para sacar las escenas que se ajustan a la configuración deseada
        yield "Metadata obtenida. Iniciando procesamiento...\n"
        scenes = yield from process_metadata(features)

        return features, scenes

    def download_data(self, features, scenes, indices):
        """Descarga los archivos .tif según las escenas obtenidas."""
        
        yield "\nObteniendo bandas necesarias para los índices seleccionados...\n"
        required_bands = determine_required_bands(indices)
        
        # Verificar qué tipos de datos necesitamos
        need_sr = any(collection.lower() == 'sr' for band, collection in required_bands.items())
        need_st = any(collection.lower() == 'st' for band, collection in required_bands.items())
        
        # Enriquecer la información de las escenas con su colección
        for scene in scenes:
            # Si no tiene colección explícita, intentar determinarla
            if 'collection' not in scene:
                feature = next((f for f in features if f.get('id') == scene.get('id')), None)
                if feature:
                    collection = feature.get('collection', 'landsat-c2l2-sr').lower()
                    scene['collection'] = collection
                else:
                    # Si no podemos determinar la colección, asumimos SR por defecto
                    scene['collection'] = 'landsat-c2l2-sr'
        
        # Mostrar estadísticas de escenas por colección
        sr_scenes = [s for s in scenes if 'sr' in s.get('collection', '').lower()]
        st_scenes = [s for s in scenes if 'st' in s.get('collection', '').lower()]
        
        yield f"Total de escenas seleccionadas: {len(scenes)}"
        yield f"Escenas SR: {len(sr_scenes)}, Escenas ST: {len(st_scenes)}"
        
        # Verificar si necesitamos bandas ST pero no tenemos escenas ST
        if need_st and not st_scenes:
            yield "Se requieren bandas de temperatura superficial (ST) pero no se encontraron escenas ST..."
            yield "Buscando escenas ST correspondientes a las escenas SR seleccionadas..."
            
            # Buscar escenas ST correspondientes a las SR
            for sr_scene in sr_scenes:
                path = sr_scene.get('path')
                row = sr_scene.get('row')
                date = sr_scene.get('date')
                
                # Buscar en los features que tengan la misma ubicación y fecha
                matching_st_features = [f for f in features 
                                      if 'st' in f.get('collection', '').lower() and
                                         f.get('properties', {}).get('landsat:wrs_path') == path and
                                         f.get('properties', {}).get('landsat:wrs_row') == row and
                                         f.get('properties', {}).get('datetime', '')[:10] == date]
                
                if matching_st_features:
                    for st_feature in matching_st_features:
                        st_scene = {
                            'id': st_feature.get('id'),
                            'path': path,
                            'row': row,
                            'date': date,
                            'cloud_cover': st_feature.get('properties', {}).get('eo:cloud_cover', sr_scene.get('cloud_cover', 100)),
                            'coverage_percent': sr_scene.get('coverage_percent', 0),
                            'collection': 'landsat-c2l2-st'
                        }
                        
                        # Añadir a la lista de escenas
                        if not any(s.get('id') == st_scene['id'] for s in scenes):
                            scenes.append(st_scene)
                            st_scenes.append(st_scene)
                            yield f"Añadida escena ST correspondiente: {st_scene['id']}"
        
        # Si necesitamos bandas SR pero no tenemos escenas SR, hacer lo mismo
        if need_sr and not sr_scenes:
            yield "Se requieren bandas de reflectancia superficial (SR) pero no se encontraron escenas SR..."
            yield "Buscando escenas SR correspondientes a las escenas ST seleccionadas..."
            
            # Buscar escenas SR correspondientes a las ST
            for st_scene in st_scenes:
                path = st_scene.get('path')
                row = st_scene.get('row')
                date = st_scene.get('date')
                
                # Buscar en los features que tengan la misma ubicación y fecha
                matching_sr_features = [f for f in features 
                                      if 'sr' in f.get('collection', '').lower() and
                                         f.get('properties', {}).get('landsat:wrs_path') == path and
                                         f.get('properties', {}).get('landsat:wrs_row') == row and
                                         f.get('properties', {}).get('datetime', '')[:10] == date]
                
                if matching_sr_features:
                    for sr_feature in matching_sr_features:
                        sr_scene = {
                            'id': sr_feature.get('id'),
                            'path': path,
                            'row': row,
                            'date': date,
                            'cloud_cover': sr_feature.get('properties', {}).get('eo:cloud_cover', st_scene.get('cloud_cover', 100)),
                            'coverage_percent': st_scene.get('coverage_percent', 0),
                            'collection': 'landsat-c2l2-sr'
                        }
                        
                        # Añadir a la lista de escenas
                        if not any(s.get('id') == sr_scene['id'] for s in scenes):
                            scenes.append(sr_scene)
                            sr_scenes.append(sr_scene)
                            yield f"Añadida escena SR correspondiente: {sr_scene['id']}"
        
        # Actualizar estadísticas
        sr_scenes = [s for s in scenes if 'sr' in s.get('collection', '').lower()]
        st_scenes = [s for s in scenes if 'st' in s.get('collection', '').lower()]
        
        yield f"Total de escenas a procesar: {len(scenes)}"
        yield f"Escenas SR: {len(sr_scenes)}, Escenas ST: {len(st_scenes)}"
        
        # Iniciar la descarga
        yield f"Iniciando descarga de las bandas requeridas..."
        base_path = yield from download_images(features, scenes, required_bands)
        
        yield "\nDescarga finalizada."
        return base_path


class ProcessingController:
    """Controlador para Procesar las imágenes y el cálculo de los índices"""

    def __init__(self, config):
        self.config = config
        self.stop_requested = False

    def generate_mosaics(self):
        """
        Genera los mosaicos y los recorta según el polígono.
        Implementa un sistema de generación por etapas para mejor control
        y retroalimentación durante el proceso.
        """
        try:
            # Paso 1: Preparar carpetas y paths
            yield "Preparando directorios para mosaicos y recortes..."
            script_dir = Path(__file__).parent
            data_path = script_dir.parent.parent / "data" / "temp" / "source"
            
            # Buscar archivos con extensión .geojson y .shp
            files = sorted(
                glob.glob(str(data_path / "*.geojson")) + glob.glob(str(data_path / "*.shp")),
                key=os.path.getmtime,
                reverse=True
            )
            
            if not files:
                raise Exception(f"No se encontró ningún archivo poligonal en: {data_path}")
                
            polygon_path = files[0]
            yield f"Usando polígono: {os.path.basename(polygon_path)}"
            
            if not os.path.exists(polygon_path):
                raise Exception(f"El archivo del polígono {polygon_path} no existe.")
                
            download_path = script_dir.parent.parent / "data" / "temp" / "downloads"
            
            # Paso 2: Obtener bandas descargadas
            yield "Identificando bandas espectrales descargadas..."
            sorted_bands = get_scenes_by_band(download_path)
            
            if not sorted_bands:
                raise Exception("No se encontraron bandas para procesar")
                
            # Información detallada de bandas encontradas
            band_info = ", ".join([f"{k}({len(v)})" for k, v in sorted_bands.items()])
            yield f"Bandas encontradas: {band_info}"
            
            # Paso 3: Crear mosaicos por banda
            processed_mosaics = {}
            output_mosaic = script_dir.parent.parent / "data" / "temp" / "processed" / "mosaic"
            
            yield "Creando mosaico para cada banda..."
            total_bands = len(sorted_bands)
            
            for i, (band, files) in enumerate(sorted_bands.items()):
                if self.stop_requested:
                    yield "Proceso cancelado por el usuario."
                    return
                    
                try:
                    yield f"[{i+1}/{total_bands}] Creando mosaico para la banda {band}..."
                    mosaic_path = build_mosaic_per_band(files, output_mosaic, band)
                    
                    if mosaic_path and os.path.exists(mosaic_path):
                        processed_mosaics[band] = mosaic_path
                        yield f"✓ Mosaico de {band} creado exitosamente"
                    else:
                        raise Exception(f"No se pudo crear el mosaico para la banda {band}")
                    
                except Exception as e:
                    yield f"⚠ Error en mosaico de banda {band}: {str(e)}"
                    
            if not processed_mosaics:
                raise Exception("No se pudo crear ningún mosaico.")
                
            # Paso 4: Recortar mosaicos con el polígono
            created_clips = {}
            clips_path = script_dir.parent.parent / "data" / "temp" / "processed" / "clip"
            
            yield "\nRecortando mosaicos con el polígono..."
            total_mosaics = len(processed_mosaics)
            
            for i, (band, mosaic_path) in enumerate(processed_mosaics.items()):
                if self.stop_requested:
                    yield "Proceso cancelado por el usuario."
                    return
                    
                try:
                    yield f"[{i+1}/{total_mosaics}] Recortando mosaico para banda {band}..."
                    clip_path = extract_mosaic_by_polygon(mosaic_path, polygon_path, clips_path)
                    
                    if clip_path is not None:
                        created_clips[band] = clip_path
                        yield f"✓ Recorte de {band} creado exitosamente"
                    else:
                        raise Exception(f"No se pudo crear el recorte para la banda {band}")
                        
                except Exception as e:
                    yield f"⚠ Error en recorte de banda {band}: {str(e)}"
                    
            # Resumen y registro
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
                yield f"\nRegistro guardado en {log_path}"
            except Exception as e:
                yield f"Error al guardar el registro: {str(e)}"
                
            yield f"\nProcesamiento completado: {len(processed_mosaics)} mosaicos y {len(created_clips)} recortes generados."
            
            return results
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(error_details)
            raise Exception(f"Error al generar mosaicos: {str(e)}")

    def calculate_indices(self, indices):
        """
        Calcula los índices espectrales y exporta los resultados.
        """
        try:
            if not indices:
                raise Exception("No se seleccionaron índices para calcular")
                
            yield f"Iniciando cálculo de índices: {', '.join(indices)}"
            
            # Llamar al envoltorio de procesamiento de índices
            yield from process_indices_from_cutouts_wrapper(indices)
            
            yield "Cálculo de índices completado exitosamente"
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(error_details)
            raise Exception(f"Error al calcular índices: {str(e)}")
            
    def stop(self):
        """Detiene el procesamiento actual de forma segura"""
        self.stop_requested = True