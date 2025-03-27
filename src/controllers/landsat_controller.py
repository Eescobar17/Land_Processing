from ..landsat.query import generate_landsat_query, fetch_stac_server
from ..landsat.downloader import determine_required_bands, download_images
from ..landsat.processing import process_metadata

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
        
        yield "Obteniendo bandas necesarias para los índices seleccionados...\n"
        required_bands = determine_required_bands(indices)

        yield "Descargando bandas espectrales...\n"
        base_path = download_images(features, scenes, required_bands)

        yield "Descarga completada con éxito."