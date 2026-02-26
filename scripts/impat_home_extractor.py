from bs4 import BeautifulSoup
import csv

# Read the HTML file
with open('impat_home.html', 'r', encoding='utf-8') as file:
    html_content = file.read()

# Parse HTML with BeautifulSoup
soup = BeautifulSoup(html_content, 'html.parser')

# Find all option tags
options = soup.find_all('option')

# Filter out the first "Choose from dropdown" option
plant_options = []
for option in options:
    value = option.get('value', '')
    text = option.text.strip()
    if text != "Choose from dropdown":  # Skip the placeholder option
        plant_options.append((value, text))

# Create CSV file
with open('plant_options.csv', 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    
    # Write header
    writer.writerow(['Value', 'Plant Name'])
    
    # Write all options
    for value, plant_name in plant_options:
        writer.writerow([value, plant_name])

print(f"Extracted {len(plant_options)} plant entries and saved to plant_options.csv")