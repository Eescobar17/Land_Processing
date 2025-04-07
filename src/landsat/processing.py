import os
import traceback
import pandas as pd
from shapely.ops import unary_union
from datetime import datetime
import geopandas as gpd
from shapely.geometry import shape, Polygon
import matplotlib.pyplot as plt
import glob
from pathlib import Path
import matplotlib.patches as mpatches
import matplotlib
from adjustText import adjust_text

def get_footprint_from_feature(feature):
    """
    Extrae la huella (footprint) de una característica (feature) de Landsat.
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

def visualize_coverage(relative_path, features, selected_scenes=None, coverage_percent=None):
    """
    Genera una visualización de la cobertura del polígono por las escenas Landsat.
    """
    
    # Leer el polígono
    gdf_polygon = gpd.read_file(relative_path)

    # Establece el backend en un modo seguro para hilos
    matplotlib.use("Agg")
    
    # Crear una figura y eje
    fig, ax = plt.subplots(figsize=(14, 12))
    
    # Definir un colormap personalizado para las escenas seleccionadas
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
              '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    # Dibujar el polígono principal
    gdf_polygon.plot(ax=ax, color='none', edgecolor='red', linewidth=2.5, zorder=3)
    
    # Obtener IDs de escenas seleccionadas si existen
    selected_ids = []
    if selected_scenes:
        selected_ids = [scene.get('id') for scene in selected_scenes]
    
    # Crear diccionario para registrar qué path/row ya están dibujados (para escenas no seleccionadas)
    path_row_drawn = {}

    # Obtener límites del polígono
    min_x, min_y, max_x, max_y = gdf_polygon.total_bounds
    buffer = max((max_x - min_x) * 0.05, (max_y - min_y) * 0.05)  # 5% del tamaño

    # Ajustar límites del gráfico
    ax.set_xlim(min_x - buffer, max_x + buffer)
    ax.set_ylim(min_y - buffer, max_y + buffer)

    # Ajustar tamaño de texto dinámicamente en función del tamaño del polígono
    text_size = max(4, min(12, (max_x - min_x) * 0.05))  # Ajuste automático

    # Lista para manejar textos con adjustText
    texts = []

    # Filtrar características por ID para dibujar primero las NO seleccionadas (fondo)
    for i, feature in enumerate(features):
        scene_id = feature.get('id', f'Escena {i+1}')
        
        # Si esta escena está en las seleccionadas, la dibujamos después
        if scene_id in selected_ids:
            continue
            
        # Obtener footprint e info
        footprint = get_footprint_from_feature(feature)
        if not footprint:
            continue
            
        props = feature.get('properties', {})
        path = props.get('landsat:wrs_path', 'N/A')
        row = props.get('landsat:wrs_row', 'N/A')
        path_row = f"{path}_{row}"
        
        # Si ya dibujamos este path/row, continuar
        if path_row in path_row_drawn:
            continue
            
        # Marcar este path/row como dibujado
        path_row_drawn[path_row] = True
        
        # Crear un GeoDataFrame para la huella
        gdf_footprint = gpd.GeoDataFrame(geometry=[footprint])
        
        # Dibujar la huella con color semitransparente
        gdf_footprint.plot(
            ax=ax, 
            color='lightgray', 
            alpha=0.2, 
            linewidth=0.5,
            edgecolor='gray',
            zorder=1
        )
        
        # Añadir una etiqueta muy pequeña con Path/Row
        centroid = footprint.centroid
        ax.text(
            centroid.x, centroid.y, 
            f"P{path}/R{row}",
            ha='center', va='center', 
            fontsize=6, 
            color='gray',
            zorder=2
        )
    
    # Ahora dibujar las escenas seleccionadas (primer plano)
    for i, scene_info in enumerate(selected_scenes or []):
        # Buscar la característica correspondiente
        scene_id = scene_info['id']
        scene_feature = None
        
        for feature in features:
            if feature.get('id') == scene_id:
                scene_feature = feature
                break
                
        if not scene_feature:
            continue
            
        # Obtener footprint
        footprint = get_footprint_from_feature(scene_feature)
        if not footprint:
            continue
            
        # Información adicional
        path = scene_info['path']
        row = scene_info['row']
        date = scene_info['date']
        cloud = scene_info['cloud_cover']
        
        # Crear un GeoDataFrame para la huella
        gdf_footprint = gpd.GeoDataFrame(geometry=[footprint])
        
        # Usar un color del ciclo de colores
        color_idx = i % len(colors)
        
        # Dibujar la huella con color distintivo
        gdf_footprint.plot(
            ax=ax, 
            color=colors[color_idx], 
            alpha=0.5, 
            linewidth=1.5,
            edgecolor='black',
            zorder=4
        )
        
        # Añadir etiqueta informativa
        centroid = footprint.centroid
        text = ax.text(
            centroid.x, centroid.y, 
            f"P{path}/R{row}\n{date}\nNubes: {cloud:.1f}%", 
            ha='center', va='center', 
            fontsize=text_size,  # Ajuste dinámico del tamaño de texto
            bbox=dict(facecolor='white', alpha=0.4, edgecolor='black', boxstyle='round,pad=0.3'),
            zorder=5
        )
        texts.append(text)
    
    # Ajustar la posición de los textos si se superponen
    adjust_text(texts, ax=ax)

    # Título y configuración
    if selected_scenes and coverage_percent:
        ax.set_title(f'Cobertura del polígono con {len(selected_scenes)} escenas y {coverage_percent:.2f}% de cobertura', fontsize=14)
    else:
        ax.set_title('Cobertura del polígono con escenas Landsat disponibles', fontsize=14)
    
    # Configuración de ejes
    ax.set_xlabel('Longitud', fontsize=12)
    ax.set_ylabel('Latitud', fontsize=12)
    ax.grid(True, linestyle='--', alpha=0.5)
    
    # Crear leyenda
    legend_elements = [
        mpatches.Patch(facecolor='red', fill=False, linewidth=2.5, label='Polígono de interés'),
        mpatches.Patch(facecolor='lightgray', alpha=0.2, linewidth=0.5, edgecolor='gray', label='Escenas disponibles')
    ]
    
    ax.legend(handles=legend_elements, loc='lower right', fontsize=10)
    
    # Información adicional
    if selected_scenes:
        # Calcular rango de fechas
        dates = [scene.get('date') for scene in selected_scenes if scene.get('date')]
        date_range = f"{min(dates)} a {max(dates)}" if dates else "No disponible"
        
        # Calcular diferencia en meses (aproximada)
        try:
            from datetime import datetime
            date_objs = [datetime.strptime(d, '%Y-%m-%d') for d in dates]
            days_diff = (max(date_objs) - min(date_objs)).days
            months_diff = days_diff // 30
            date_diff = f"{months_diff} meses ({days_diff} días)"
        except:
            date_diff = "No calculable"
        
        info_text = (
            f"Escenas seleccionadas: {len(selected_scenes)}\n"
            f"Cobertura total: {coverage_percent:.2f}%\n"
            f"Rango de fechas: {date_range}\n"
            f"Diferencia temporal: {date_diff}\n"
            f"Nubosidad promedio: {sum(s['cloud_cover'] for s in selected_scenes) / len(selected_scenes):.2f}%"
        )
        
        plt.figtext(0.02, 0.02, info_text, fontsize=10, bbox=dict(facecolor='white', alpha=0.8, boxstyle='round'))
    
    # Guardar la figura
    script_dir = Path(__file__).parent 
    output_file = script_dir.parent.parent / "data" / "exports" / "coverage_map.png"
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()
    
    return output_file

def analyze_coverage(relative_path, features, min_area, window_days=120, delete_out_range=True):
    """
    Analiza la cobertura del polígono por las escenas Landsat con enfoque en Path/Row.
    Prioriza cobertura espacial, luego minimiza nubosidad y finalmente ajusta coherencia temporal.
    """
    
    print("Analizando cobertura con enfoque optimizado en Path/Row...")

    # Leer el polígono
    gdf_polygon = gpd.read_file(relative_path)
    polygon = gdf_polygon.geometry.iloc[0]
    polygon_area = polygon.area
    
    # Lista para almacenar información de todas las escenas
    all_scenes = []
    
    # Extraer información de todas las escenas
    for i, feature in enumerate(features):
        footprint = get_footprint_from_feature(feature)
        if not footprint:
            raise Exception(f"No se pudo encontrar la huella de la escena: {feature.get('id', f'Escena {i+1}')}")
        
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
        msg = "No se encontraron escenas con intersección significativa con el polígono."
        print(msg)
        raise Exception(msg)
        # return {
        #     'total_coverage_percent': 0,
        #     'coverage_by_scene': pd.DataFrame(),
        #     'scenes_needed': [],
        #     'uncovered_percent': 100
        # }

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
    best_df = pd.DataFrame(best_rows).reset_index(drop=True)
    # # print(best_df[["path_row", "date_obj", "cloud_cover"]])

    # Calcular cobertura final con las escenas seleccionadas
    if not best_df.empty:
        selected_footprints = best_df['footprint'].dropna().tolist()  # Extraer footprints y eliminar nulos
        final_combined = unary_union(selected_footprints)
        final_intersection = polygon.intersection(final_combined)
        final_coverage = (final_intersection.area / polygon_area) * 100
    else:
        final_coverage = 0

    # # print(f"\nNOTA: Se cubrió el {final_coverage:.2f}% del área del polígono con un total de {len(best_rows)} escenas.")
    
    # Preparar los datos de salida
    selected_scenes = []

    for _, scene in best_df.iterrows():
        selected_scenes.append({
            'id': scene['id'],
            'path': scene['path'],
            'row': scene['row'],
            'date': scene['date_str'],
            'cloud_cover': scene['cloud_cover'],
            'coverage_percent': scene['coverage_percent']
        })

    return {
        'total_coverage_percent': final_coverage,
        'coverage_by_scene': scenes_df.drop(columns=['footprint'], errors='ignore'),
        'scenes_needed': selected_scenes,
        'uncovered_percent': 100 - final_coverage
    }

def process_metadata(features, min_area=0):
    """
    Procesa los datos según la configuración actual.
    """

    msg = ""
    scenes = dict()

    # Ruta basada en la ubicación del script
    script_dir = Path(__file__).parent  # Carpeta donde está el script
    data_path = script_dir.parent.parent / "data" / "temp" / "source"  # Ruta a la carpeta con los archivos

    # Buscar archivos con extensión .geojson y .shp
    files = sorted(
        glob.glob(str(data_path / "*.geojson")) + glob.glob(str(data_path / "*.shp")), 
        key=os.path.getmtime, 
        reverse=True
    )

    if not files:
        raise Exception(f"No se encontró ningún archivo en: {data_path}")
    
    # Se selecciona el primer archivo
    relative_path = files[0]

    if not features:
        msg = """No se encontraron imágenes con los criterios especificados.
        \nSugerencias:
        1. Amplía el rango de fechas.
        2. Aumenta el porcentaje de cobertura de nubes permitido.
        3. Verifica que el polígono está en un área con cobertura Landsat.
        """
        print(msg)
        yield "No se encontraron imágenes con los criterios especificados."
        raise Exception(msg)

    try:
        msg = f"Se encontraron {len(features)} imágenes que cumplen con los criterios."
        print(msg)
        yield msg
        
        # 6. Mostrar información de las imágenes encontradas
        print("\nInformación de las imágenes encontradas (hasta 50):")
        print("-" * 100)
        print(f"{'#':<4}{'ID':<50}{'Fecha':<15}{'Nubes':<10}{'Path':<8}{'Row':<6}")
        print("-" * 100)

        max_scenes_to_show = min(50, len(features))
        for i, feature in enumerate(features[:max_scenes_to_show]):
            img_id = feature.get('id', 'Desconocido')
            properties = feature.get('properties', {})
            cloud = properties.get('eo:cloud_cover', 'N/A')
            date = properties.get('datetime', 'Fecha desconocida')[:10]  # Solo la parte de fecha
            path = properties.get('landsat:wrs_path', 'N/A')
            row = properties.get('landsat:wrs_row', 'N/A')
            
            print(f"{i+1:<4}{img_id:<50}{date:<15}{cloud:<10.2f}{path:<8}{row:<6}")

        if len(features) > max_scenes_to_show:
            print(f"\nSe omitieron {len(features) - max_scenes_to_show} imágenes adicionales.")
        
        # 7. Analizar cobertura y descargar las escenas necesarias
        if len(features) > 0:
            msg = "\nAnalizando cobertura del polígono..."
            print(msg)
            yield msg
            
            # Analizar la cobertura
            coverage_info = analyze_coverage(relative_path, features, min_area)

            msg = f"""\nCobertura total: {coverage_info['total_coverage_percent']:.2f}%\nSe necesitan {len(coverage_info['scenes_needed'])} escenas para cubrir el polígono"""
            print(msg)
            yield msg

            # Obtener las escenas necesarias para la cobertura óptima
            scenes_needed = coverage_info['scenes_needed']
            coverage_percent = coverage_info['total_coverage_percent']

            # Generar visualización de cobertura
            try:
                coverage_map = visualize_coverage(relative_path, features, scenes_needed, coverage_percent)
                msg = f"\nMapa de Cobertura generado: {coverage_map}"
            except Exception as e:
                msg = "No se pudo generar un Mapa de Cobertura"

            print(msg)
            yield msg

            scenes = scenes_needed

        yield "Proceso de captura de metadata finalizado"
        return scenes

    except Exception as e:
        msg = f"Error durante el procesamiento: {str(e)}"
        print(msg)
        traceback.print_exc()
        raise