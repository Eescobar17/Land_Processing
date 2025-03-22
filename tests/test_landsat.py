from src.landsat import generate_landsat_query, fetch_stac_server, download_images

def main():
    file_path = "data/downloads/test_data.geojson"
    start_date = "2024-08-01"
    end_date = "2024-08-01"
    query = generate_landsat_query(file_path, start_date, end_date)
    features = fetch_stac_server(query)

    download_images([features[0]])

if __name__ == "__main__":
    main()