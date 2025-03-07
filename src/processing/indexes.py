import rasterio
import numpy as np

def read_band(file_path):
    """Reads a single band from a .tif file and returns it as a numpy array."""
    with rasterio.open(file_path) as dataset:
        return dataset.read(1).astype(np.float32)

def calculate_ndvi(nir_band, red_band):
    """Calculates the Normalized Difference Vegetation Index (NDVI)."""
    ndvi = (nir_band - red_band) / (nir_band + red_band + 1e-10)  # Avoid division by zero
    return ndvi

def calculate_ndsi(swir_band, green_band):
    """Calculates the Normalized Difference Snow Index (NDSI)."""
    ndsi = (green_band - swir_band) / (green_band + swir_band + 1e-10)
    return ndsi

def calculate_ndwi(nir_band, green_band):
    """Calculates the Normalized Difference Water Index (NDWI)."""
    ndwi = (green_band - nir_band) / (green_band + nir_band + 1e-10)
    return ndwi

def calculate_bsi(nir_band, red_band, swir1_band, blue_band):
    """Calculates the Bare Soil Index (BSI)."""
    bsi = ((swir1_band + red_band) - (nir_band + blue_band)) / ((swir1_band + red_band) + (nir_band + blue_band) + 1e-10)
    return bsi

def calculate_lst(tirs_band, metadata):
    """Calculates the Land Surface Temperature (LST) using the thermal infrared (TIRS) band and metadata."""
    # Constants
    K1 = metadata['K1_CONSTANT']  # Extract from metadata
    K2 = metadata['K2_CONSTANT']
    emissivity = 0.97  # Approximate value for vegetation

    # Convert to radiance
    radiance = K1 / (np.exp(K2 / (tirs_band + 273.15)) - 1)

    # Convert to temperature in Celsius
    lst = (radiance / emissivity) - 273.15
    return lst
