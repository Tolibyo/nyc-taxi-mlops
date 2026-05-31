
import requests
from pathlib import Path

def download_tlc_data(taxi_type, year, month, output_dir):

    response = requests.get(f'https://d37ci6vzurychx.cloudfront.net/trip-data/{taxi_type}_tripdata_{year}-{month:02d}.parquet')
    response.raise_for_status()
    
    file_path = Path(output_dir) / f"{taxi_type}_tripdata_{year}-{month:02d}.parquet"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
  
    with open(file_path, 'wb') as f:
        f.write(response.content)


for month in range(1, 13):
    print(f"Downloading 2024-{month:02d}...")
    download_tlc_data("yellow", 2024, month, "data/raw/yellow/2024")
        
        
            
