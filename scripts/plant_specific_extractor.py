import json
import re
from bs4 import BeautifulSoup

def extract_plant_data_clean_all(html_content):
    """
    Clean extraction for all fields including system_of_medicine
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    result = {
        "plant_name": "",
        "common_name": "",
        "synonymous_names": "",
        "system_of_medicine": "",
        "phytochemicals": []
    }
    
    # Get plant name from h5
    h5 = soup.find('h5')
    if h5:
        result["plant_name"] = h5.get_text(strip=True)
    
    # Get all text from the page
    all_text = soup.get_text()
    
    # Define the fields we want to extract and their order
    # This is IMPORTANT: fields appear in this order in the HTML
    field_order = [
        ("Common name:", "common_name"),
        ("Synonymous names:", "synonymous_names"), 
        ("System of medicine:", "system_of_medicine")
    ]
    
    # Extract each field by finding its position and the position of the next field
    for i, (field_label, field_key) in enumerate(field_order):
        if field_label in all_text:
            start_idx = all_text.find(field_label) + len(field_label)
            
            # Find where this field ends (start of next field or end of string)
            end_idx = len(all_text)
            
            # Look for the next field in the order
            for j in range(i + 1, len(field_order)):
                next_field_label = field_order[j][0]
                next_pos = all_text.find(next_field_label, start_idx)
                if next_pos != -1 and next_pos < end_idx:
                    end_idx = next_pos
                    break
            
            # Also check for "More Information:" which comes after all fields
            more_info_pos = all_text.find("More Information:", start_idx)
            if more_info_pos != -1 and more_info_pos < end_idx:
                end_idx = more_info_pos
            
            # Extract and clean the value
            value = all_text[start_idx:end_idx].strip()
            # Clean up whitespace
            value = ' '.join(value.split())
            result[field_key] = value
    
    # Alternative method if the above doesn't work
    # Sometimes the text extraction doesn't work perfectly, so let's try HTML parsing
    if not result["common_name"] or len(result["common_name"]) > 100:
        # Reset the values
        result["common_name"] = ""
        result["synonymous_names"] = ""
        result["system_of_medicine"] = ""
        
        # Find the container with plant details
        container = soup.find('div', class_='col-lg-8')
        if container:
            html_str = str(container)
            
            # Extract using regex that stops at the next HTML tag or known field
            patterns = {
                "common_name": r'Common name:</strong>\s*([^<]+?)(?=\s*<br>|\s*<strong>Synonymous names:)',
                "synonymous_names": r'Synonymous names:</strong>\s*([^<]+?)(?=\s*<br>|\s*<strong>System of medicine:)',
                "system_of_medicine": r'System of medicine:</strong>\s*([^<]+?)(?=\s*<br>|\s*<strong>More Information:)'
            }
            
            for key, pattern in patterns.items():
                match = re.search(pattern, html_str, re.IGNORECASE | re.DOTALL)
                if match:
                    result[key] = match.group(1).strip()
    
    # Final cleanup - remove any remaining field names from the values
    field_names_to_remove = ["Common name:", "Synonymous names:", "System of medicine:", 
                           "Kingdom:", "Family:", "Group:", "More Information:"]
    
    for key in ["common_name", "synonymous_names", "system_of_medicine"]:
        if key in result:
            value = result[key]
            # Remove any field names that might be at the beginning
            for field in field_names_to_remove:
                if value.startswith(field):
                    value = value[len(field):].strip()
                # Also check if field appears anywhere in the value
                if field in value:
                    # Split at the field name and take only the first part
                    value = value.split(field)[0].strip()
            result[key] = value
    
    # Extract table data
    result["phytochemicals"] = []
    table = soup.find('table', class_='phytochem table')
    
    if table:
        rows = table.find_all('tr')[1:]  # Skip header row
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 5:
                phytochemical = {
                    "indian_medicinal_plant": cols[0].get_text(strip=True),
                    "plant_part": cols[1].get_text(strip=True),
                    "imppat_phytochemical_identifier": cols[2].get_text(strip=True),
                    "phytochemical_name": cols[3].get_text(strip=True),
                    "references": cols[4].get_text(strip=True)
                }
                result["phytochemicals"].append(phytochemical)
    
    return result

# Even simpler version that should definitely work
def extract_all_fields_simple(html_content):
    """
    Simple extraction that works for all three fields
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    result = {
        "plant_name": "",
        "common_name": "",
        "synonymous_names": "",
        "system_of_medicine": "",
        "phytochemicals": []
    }
    
    # Get plant name
    h5 = soup.find('h5')
    if h5:
        result["plant_name"] = h5.get_text(strip=True)
    
    # Convert to string for regex parsing
    html_str = str(soup)
    
    # Pattern to find all fields in one go
    # Looks for: <strong>Field Name:</strong> Value <br>
    pattern = r'<strong>Common name:</strong>\s*([^<]+).*?<strong>Synonymous names:</strong>\s*([^<]+).*?<strong>System of medicine:</strong>\s*([^<]+)'
    
    match = re.search(pattern, html_str, re.DOTALL)
    if match:
        result["common_name"] = match.group(1).strip()
        result["synonymous_names"] = match.group(2).strip()
        result["system_of_medicine"] = match.group(3).strip()
        
        # Clean each value - remove any trailing <br> or other tags
        for key in ["common_name", "synonymous_names", "system_of_medicine"]:
            value = result[key]
            # Remove anything after <br
            if '<br' in value:
                value = value.split('<br')[0].strip()
            # Remove anything after the next <strong
            if '<strong' in value:
                value = value.split('<strong')[0].strip()
            result[key] = value
    
    # If regex didn't work, try text-based extraction
    if not result["common_name"]:
        # Get text and split by lines
        text = soup.get_text()
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('Common name:'):
                # Extract value after the label
                value = line.replace('Common name:', '').strip()
                # Remove any other field labels that might be in the same line
                for other_label in ['Synonymous names:', 'System of medicine:', 'More Information:']:
                    if other_label in value:
                        value = value.split(other_label)[0].strip()
                result["common_name"] = value
            
            elif line.startswith('Synonymous names:'):
                value = line.replace('Synonymous names:', '').strip()
                for other_label in ['System of medicine:', 'More Information:']:
                    if other_label in value:
                        value = value.split(other_label)[0].strip()
                result["synonymous_names"] = value
            
            elif line.startswith('System of medicine:'):
                value = line.replace('System of medicine:', '').strip()
                if 'More Information:' in value:
                    value = value.split('More Information:')[0].strip()
                result["system_of_medicine"] = value
    
    # Extract table data
    table = soup.find('table', class_='phytochem table')
    if table:
        rows = table.find_all('tr')[1:]  # Skip header
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 5:
                phytochemical = {
                    "indian_medicinal_plant": cols[0].get_text(strip=True),
                    "plant_part": cols[1].get_text(strip=True),
                    "imppat_phytochemical_identifier": cols[2].get_text(strip=True),
                    "phytochemical_name": cols[3].get_text(strip=True),
                    "references": cols[4].get_text(strip=True)
                }
                result["phytochemicals"].append(phytochemical)
    
    return result

# Most reliable version using BeautifulSoup's tree navigation
def extract_fields_using_soup_navigation(html_content):
    """
    Use BeautifulSoup's tree navigation to extract fields precisely
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    result = {
        "plant_name": "",
        "common_name": "",
        "synonymous_names": "",
        "system_of_medicine": "",
        "phytochemicals": []
    }
    
    # Get plant name
    h5 = soup.find('h5')
    if h5:
        result["plant_name"] = h5.get_text(strip=True)
    
    # Find the container
    container = soup.find('div', class_='col-lg-8')
    
    if container:
        # Find all strong tags and extract their next siblings
        strong_tags = container.find_all('strong')
        
        for strong in strong_tags:
            text = strong.get_text(strip=True)
            
            if text == 'Common name:':
                # Get the text immediately after this strong tag
                next_node = strong.next_sibling
                if next_node:
                    value = str(next_node).strip()
                    # Clean the value
                    result["common_name"] = clean_extracted_value(value)
            
            elif text == 'Synonymous names:':
                next_node = strong.next_sibling
                if next_node:
                    value = str(next_node).strip()
                    result["synonymous_names"] = clean_extracted_value(value)
            
            elif text == 'System of medicine:':
                next_node = strong.next_sibling
                if next_node:
                    value = str(next_node).strip()
                    result["system_of_medicine"] = clean_extracted_value(value)
    
    # Extract table data
    table = soup.find('table', class_='phytochem table')
    if table:
        rows = table.find_all('tr')[1:]  # Skip header
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 5:
                phytochemical = {
                    "indian_medicinal_plant": cols[0].get_text(strip=True),
                    "plant_part": cols[1].get_text(strip=True),
                    "imppat_phytochemical_identifier": cols[2].get_text(strip=True),
                    "phytochemical_name": cols[3].get_text(strip=True),
                    "references": cols[4].get_text(strip=True)
                }
                result["phytochemicals"].append(phytochemical)
    
    return result

def clean_extracted_value(value):
    """
    Clean an extracted value by removing HTML and stopping at next field
    """
    # Remove any HTML tags
    soup = BeautifulSoup(value, 'html.parser')
    cleaned = soup.get_text()
    
    # List of field names that might appear
    field_names = [
        'Common name:', 'Synonymous names:', 'System of medicine:',
        'Kingdom:', 'Family:', 'Group:', 'More Information:'
    ]
    
    # Find the earliest occurrence of any field name
    earliest = len(cleaned)
    for field in field_names:
        idx = cleaned.find(field)
        if idx != -1 and idx < earliest:
            earliest = idx
    
    # If we found a field name, cut the text there
    if earliest < len(cleaned):
        cleaned = cleaned[:earliest].strip()
    
    return cleaned

# Final working solution - tested approach
def extract_plant_data_final_solution(html_content):
    """
    Final solution that extracts all three fields cleanly
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    result = {
        "plant_name": "",
        "common_name": "",
        "synonymous_names": "",
        "system_of_medicine": "",
        "phytochemicals": []
    }
    
    # Get plant name
    h5 = soup.find('h5')
    if h5:
        result["plant_name"] = h5.get_text(strip=True)
    
    # Method 1: Direct HTML parsing
    # Find the container
    container = soup.find('div', class_='col-lg-8')
    
    if container:
        # Convert to string
        html_str = str(container)
        
        # Use regex to find the section with all three fields
        # The pattern captures everything between h5 and the next div or table
        section_pattern = r'<h5>.*?</h5>(.*?)(?:<div|</div>|<table)'
        section_match = re.search(section_pattern, html_str, re.DOTALL)
        
        if section_match:
            section_html = section_match.group(1)
            section_soup = BeautifulSoup(section_html, 'html.parser')
            section_text = section_soup.get_text()
            
            # Now parse the text for each field
            # The fields appear in this order:
            # Kingdom: ... Family: ... Group: ... Common name: ... Synonymous names: ... System of medicine: ...
            
            # Extract Common name
            if 'Common name:' in section_text:
                # Find Common name and get text until next field
                start = section_text.find('Common name:') + len('Common name:')
                # Look for next field
                next_fields = ['Synonymous names:', 'System of medicine:', 'More Information:']
                end = len(section_text)
                for field in next_fields:
                    pos = section_text.find(field, start)
                    if pos != -1 and pos < end:
                        end = pos
                
                result["common_name"] = section_text[start:end].strip()
            
            # Extract Synonymous names
            if 'Synonymous names:' in section_text:
                start = section_text.find('Synonymous names:') + len('Synonymous names:')
                next_fields = ['System of medicine:', 'More Information:']
                end = len(section_text)
                for field in next_fields:
                    pos = section_text.find(field, start)
                    if pos != -1 and pos < end:
                        end = pos
                
                result["synonymous_names"] = section_text[start:end].strip()
            
            # Extract System of medicine
            if 'System of medicine:' in section_text:
                start = section_text.find('System of medicine:') + len('System of medicine:')
                next_fields = ['More Information:']
                end = len(section_text)
                for field in next_fields:
                    pos = section_text.find(field, start)
                    if pos != -1 and pos < end:
                        end = pos
                
                result["system_of_medicine"] = section_text[start:end].strip()
    
    # Method 2: Fallback - parse the entire text
    if not result["common_name"] or not result["synonymous_names"] or not result["system_of_medicine"]:
        all_text = soup.get_text()
        
        # Simple sequential extraction
        fields_to_extract = [
            ("Common name:", ["Synonymous names:", "System of medicine:", "More Information:"], "common_name"),
            ("Synonymous names:", ["System of medicine:", "More Information:"], "synonymous_names"),
            ("System of medicine:", ["More Information:"], "system_of_medicine")
        ]
        
        for field_label, next_fields, result_key in fields_to_extract:
            if field_label in all_text:
                start_idx = all_text.find(field_label) + len(field_label)
                
                # Find the end (start of next field)
                end_idx = len(all_text)
                for next_field in next_fields:
                    pos = all_text.find(next_field, start_idx)
                    if pos != -1 and pos < end_idx:
                        end_idx = pos
                
                value = all_text[start_idx:end_idx].strip()
                # Clean whitespace
                value = ' '.join(value.split())
                result[result_key] = value
    
    # Extract table data
    table = soup.find('table', class_='phytochem table')
    if table:
        rows = table.find_all('tr')[1:]  # Skip header
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 5:
                phytochemical = {
                    "indian_medicinal_plant": cols[0].get_text(strip=True),
                    "plant_part": cols[1].get_text(strip=True),
                    "imppat_phytochemical_identifier": cols[2].get_text(strip=True),
                    "phytochemical_name": cols[3].get_text(strip=True),
                    "references": cols[4].get_text(strip=True)
                }
                result["phytochemicals"].append(phytochemical)
    
    return result

# Main function to test and save
if __name__ == "__main__":
    # Read your HTML file
    with open("plant_0001_Abelmoschus_esculentus.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    
    print("Testing extraction of all three fields...")
    print("-" * 50)
    
    # Test Method 1
    print("\nMethod 1 - Clean extraction:")
    data1 = extract_plant_data_clean_all(html_content)
    print(f"Common name: '{data1['common_name']}'")
    print(f"Synonymous names: '{data1['synonymous_names']}'")
    print(f"System of medicine: '{data1['system_of_medicine']}'")
    print(f"Phytochemicals: {len(data1['phytochemicals'])} entries")
    
    # Test Method 2
    print("\nMethod 2 - Simple extraction:")
    data2 = extract_all_fields_simple(html_content)
    print(f"Common name: '{data2['common_name']}'")
    print(f"Synonymous names: '{data2['synonymous_names']}'")
    print(f"System of medicine: '{data2['system_of_medicine']}'")
    print(f"Phytochemicals: {len(data2['phytochemicals'])} entries")
    
    # Test Method 3
    print("\nMethod 3 - Soup navigation:")
    data3 = extract_fields_using_soup_navigation(html_content)
    print(f"Common name: '{data3['common_name']}'")
    print(f"Synonymous names: '{data3['synonymous_names']}'")
    print(f"System of medicine: '{data3['system_of_medicine']}'")
    print(f"Phytochemicals: {len(data3['phytochemicals'])} entries")
    
    # Test Method 4 (Final)
    print("\nMethod 4 - Final solution:")
    data4 = extract_plant_data_final_solution(html_content)
    print(f"Common name: '{data4['common_name']}'")
    print(f"Synonymous names: '{data4['synonymous_names']}'")
    print(f"System of medicine: '{data4['system_of_medicine']}'")
    print(f"Phytochemicals: {len(data4['phytochemicals'])} entries")
    
    # Choose the best result
    best_data = None
    for data in [data4, data3, data2, data1]:
        if (data["common_name"] and len(data["common_name"]) < 50 and 
            data["synonymous_names"] and len(data["synonymous_names"]) < 100 and
            data["system_of_medicine"] and len(data["system_of_medicine"]) < 50):
            best_data = data
            break
    
    if not best_data:
        best_data = data4  # Fallback
    
    # Save to JSON
    output_file = "plant_data_all_fields.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(best_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nBest data saved to {output_file}")
    print("\nFinal extracted values:")
    print(f"Common name: {best_data['common_name']}")
    print(f"Synonymous names: {best_data['synonymous_names']}")
    print(f"System of medicine: {best_data['system_of_medicine']}")