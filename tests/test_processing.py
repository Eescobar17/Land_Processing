from src.processing import read_band, calculate_ndvi, calculate_ndsi

# Load bands (Example: Landsat 8 bands)
nir = read_band("data/downloads/B5.tif")
red = read_band("data/downloads/B4.tif")
swir = read_band("data/downloads/B6.tif")
green = read_band("data/downloads/B3.tif")
blue = read_band("data/downloads/B2.tif")

# Compute indexes
ndvi = calculate_ndvi(nir, red)
ndsi = calculate_ndsi(swir, green)

print("NDVI and NDSI calculated successfully.")