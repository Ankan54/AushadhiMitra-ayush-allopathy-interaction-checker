import requests
import csv
import time
from urllib.parse import urljoin

def fetch_plants_with_limit(limit=1):
    """Fetch plants with a limit on how many to process"""
    base_url = 'https://cb.imsc.res.in'
    input_csv = 'plant_options.csv'
    
    # Read all plant URLs from CSV
    plants = []
    with open(input_csv, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            plants.append(row)
    
    print(f"Found {len(plants)} plants in CSV")
    print(f"Will process first {limit} plant(s)\n")
    
    # Headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    }
    
    for i in range(min(limit, len(plants))):
        plant = plants[i]
        print(f"\n[#{i+1}] Processing: {plant['Plant Name']}")
        
        full_url = urljoin(base_url, plant['Value'])
        
        try:
            response = requests.get(full_url, headers=headers, timeout=30)
            
            # Save the HTML
            filename = f"plant_{i+1:04d}_{plant['Plant Name'].replace(' ', '_')}.html"
            with open(filename, 'wb') as f:
                f.write(response.content)
            
            print(f"  Status: {response.status_code}")
            print(f"  Saved: {filename}")
            
            # Add a small delay between requests (optional)
            if i < limit - 1:  # Don't delay after the last one
                time.sleep(1)
                
        except Exception as e:
            print(f"  Error: {e}")
    
    print(f"\n✅ Processed {min(limit, len(plants))} plant(s)")

# You can change the limit here
if __name__ == "__main__":
    # Process only 1 plant for testing
    fetch_plants_with_limit(limit=1)
    
    # To process more, change the limit:
    # fetch_plants_with_limit(limit=5)  # Process 5 plants
    # fetch_plants_with_limit(limit=10) # Process 10 plants
    # fetch_plants_with_limit(limit=0)  # Process ALL plants (no limit)