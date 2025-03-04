import os
import requests
from bs4 import BeautifulSoup
from .config import USGS_USERNAME, USGS_PASSWORD

LOGIN_URL = "https://ers.cr.usgs.gov/login"

def login_usgs():
    """Logs into the USGS system and returns an authenticated session."""
    session = requests.Session()
    
    # Get the login page to extract the CSRF token
    response = session.get(LOGIN_URL)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'html5lib')
    csrf_token = soup.find('input', attrs={'name': 'csrf'})['value']

    # Login form data
    login_data = {
        "username": USGS_USERNAME,
        "password": USGS_PASSWORD,
        "csrf": csrf_token
    }

    # Send the login request
    login_response = session.post(LOGIN_URL, data=login_data)
    login_response.raise_for_status()

    if login_response.status_code == 200:
        print("Successfully logged into USGS")
    else:
        print("Authentication failed")

    return session

def download_images(features, download_path="data/downloads"):
    """Downloads Landsat images using authenticated USGS access."""
    os.makedirs(download_path, exist_ok=True)
    session = login_usgs()

    for feat in features:
        url = feat['assets']['blue']['href']
        file_name = os.path.join(download_path, os.path.basename(url))

        # Download the image with authentication
        with session.get(url, stream=True) as response:
            response.raise_for_status()
            with open(file_name, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
        print(f"Downloaded: {file_name}")