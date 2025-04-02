from ..landsat import generate_landsat_query, fetch_stac_server, determine_required_bands, download_images, process_metadata, generate_mosaics_and_clips, process_indices_from_cutouts_wrapper

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
        """Descarga los archivos .tif según las escenas obtenidos."""
        
        yield "\nObteniendo bandas necesarias para los índices seleccionados...\n"
        required_bands = determine_required_bands(indices)

        yield "Descargando bandas espectrales..."
        base_path = yield from download_images(features, scenes, required_bands)

        yield "\nDescarga Finalizada."
        return base_path
    

class ProcessingController:
    """Controlador para Procesar las imágenes y el cálculo de los índices"""

    def __init__(self, config):
        self.config = config

    def generate_mosaics(self):
        """Genera los mosaicos y los recorta según el polígono"""
        
        yield "Iniciando proceso de creación de mosaicos y recortes...\n"
        yield from generate_mosaics_and_clips()

    def calculate_indices(self, indices):
        """Calcula los índices y exporta los datos"""

        yield "Calculando índices...\n"
        yield from process_indices_from_cutouts_wrapper(indices)
