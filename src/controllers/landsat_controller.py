from ..landsat.query import generate_landsat_query, fetch_stac_server
from ..landsat.downloader import download_images
from ..landsat.processing import process_metadata

class LandsatController:
    """Controlador para gestionar la búsqueda y descarga de imágenes Landsat."""
    
    def __init__(self, config):
        self.config = config

    def fetch_data(self):
        """Genera la consulta STAC y la ejecuta para obtener los metadatos."""
        
        # Construcción del query a partir de la configuración
        query = generate_landsat_query(**self.config)
        
        # Obtención de la metadata
        features = fetch_stac_server(query)

        # Procesar metadatos para sacar las escenas que se ajustan a la configuración deseada
        process_metadata(features)

        return True

    def download(self, assets):
        """Descarga los archivos .tif según los assets obtenidos."""
        return download_images(assets, self.config)
