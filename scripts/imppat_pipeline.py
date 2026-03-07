"""
IMPPAT Phytochemical Data Extraction Pipeline
==============================================
Downloads plant pages from IMPPAT website, extracts phytochemical data,
then downloads and parses detailed phytochemical pages (summary, physicochemical,
drug-likeness, ADMET, chemical descriptors).

Output:
  - impat_webpages/{plant_name}/  -> downloaded HTML files
  - impat_jsons/{plant_name}/     -> single JSON with all extracted data
"""

import requests
import csv
import json
import os
import re
import time
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
BASE_URL = "https://cb.imsc.res.in"
CSV_FILE = "plant_options.csv"
WEBPAGES_DIR = "impat_webpages"
JSONS_DIR = "impat_jsons"
REQUEST_DELAY = 1  # seconds between requests
COOLDOWN_EVERY = 50  # cooldown after this many requests
COOLDOWN_SECONDS = 60  # seconds to wait during cooldown

# Global request counter
_request_count = 0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}

# Phytochemical detail page URL templates
PHYTO_URLS = {
    "summary":          "/imppat/phytochemical-detailedpage/{id}",
    "physicochemical":  "/imppat/physicochemicalproperties/{id}",
    "drug_likeness":    "/imppat/druglikeproperties/{id}",
    "admet":            "/imppat/admetproperties/{id}",
    "descriptors":      "/imppat/chemicaldescriptors/{id}",
}


# ─────────────────────────────────────────────
# Directory helpers
# ─────────────────────────────────────────────
def safe_dirname(name):
    """Convert a plant name to a safe directory name."""
    return name.strip().replace(" ", "_").replace("/", "_").replace("\\", "_")


def setup_directories(plant_name):
    """Create output directories for a given plant. Returns (webpages_path, jsons_path)."""
    dirname = safe_dirname(plant_name)
    wp = os.path.join(WEBPAGES_DIR, dirname)
    jp = os.path.join(JSONS_DIR, dirname)
    os.makedirs(wp, exist_ok=True)
    os.makedirs(jp, exist_ok=True)
    return wp, jp


# ─────────────────────────────────────────────
# HTTP helper
# ─────────────────────────────────────────────
def download_page(url, save_path=None, retries=3):
    """
    Download a page with retries. Optionally saves to disk.
    Returns the HTML content as a string, or None on failure.
    Automatically triggers a cooldown pause after every COOLDOWN_EVERY requests.
    """
    global _request_count

    for attempt in range(1, retries + 1):
        try:
            # Check if cooldown is needed before making the request
            _request_count += 1
            if _request_count % COOLDOWN_EVERY == 0:
                print(f"\n    ⏳ Cooldown: {COOLDOWN_SECONDS}s pause after {_request_count} requests...")
                time.sleep(COOLDOWN_SECONDS)
                print(f"    ▶ Resuming...")

            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code != 200:
                print(f"    ⚠ HTTP {resp.status_code} for {url} (attempt {attempt}/{retries})")
                time.sleep(REQUEST_DELAY)
                continue

            html = resp.text
            if save_path:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(html)

            return html

        except Exception as e:
            print(f"    ⚠ Error downloading {url}: {e} (attempt {attempt}/{retries})")
            time.sleep(REQUEST_DELAY)

    print(f"    ✖ Failed to download {url} after {retries} attempts")
    return None


# ─────────────────────────────────────────────
# Plant page extractor
# ─────────────────────────────────────────────
def extract_plant_data(html_content):
    """
    Extract plant-level information and phytochemical list from a plant details page.
    Returns dict with: plant_name, common_name, synonymous_names,
                       system_of_medicine, phytochemicals (list).
    """
    soup = BeautifulSoup(html_content, "html.parser")

    result = {
        "plant_name": "",
        "common_name": "",
        "synonymous_names": "",
        "system_of_medicine": "",
        "phytochemicals": [],
    }

    # ── Plant name from <h5> ──
    h5 = soup.find("h5")
    if h5:
        result["plant_name"] = h5.get_text(strip=True)

    # ── Extract metadata fields ──
    # Strategy: find <strong> labels inside the info container and grab adjacent text.
    # This is more robust than the regex-based approach in the old extractor.
    container = soup.find("div", class_="col-lg-8")
    if container:
        strong_tags = container.find_all("strong")
        for st in strong_tags:
            label = st.get_text(strip=True)
            if label.startswith("Common name"):
                val = _get_text_after_strong(st)
                if val:
                    result["common_name"] = val
            elif label.startswith("Synonymous name"):
                val = _get_text_after_strong(st)
                if val:
                    result["synonymous_names"] = val
            elif label.startswith("System of medicine"):
                val = _get_text_after_strong(st)
                if val:
                    result["system_of_medicine"] = val

    # Fallback: if the container-based approach didn't work, parse full text
    if not result["common_name"] and not result["synonymous_names"]:
        _extract_from_full_text(soup, result)

    # ── Phytochemical table ──
    table = soup.find("table", class_="phytochem table")
    if not table:
        # Try finding by looking for table headers
        for t in soup.find_all("table"):
            headers = [th.get_text(strip=True) for th in t.find_all("th")]
            if "IMPPAT Phytochemical identifier" in headers or "Phytochemical name" in headers:
                table = t
                break

    if table:
        rows = table.find_all("tr")[1:]  # Skip header
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 5:
                phyto = {
                    "indian_medicinal_plant": cols[0].get_text(strip=True),
                    "plant_part": cols[1].get_text(strip=True),
                    "imppat_phytochemical_identifier": cols[2].get_text(strip=True),
                    "phytochemical_name": cols[3].get_text(strip=True),
                    "references": cols[4].get_text(strip=True),
                }
                result["phytochemicals"].append(phyto)

    return result


def _get_text_after_strong(strong_tag):
    """Get the text content immediately after a <strong> tag until the next <strong> or <br>."""
    texts = []
    for sibling in strong_tag.next_siblings:
        if sibling.name == "strong":
            break
        if sibling.name == "br":
            # If we already have text, stop; otherwise skip leading <br>
            if texts:
                break
            continue
        text = sibling.get_text(strip=True) if hasattr(sibling, "get_text") else str(sibling).strip()
        if text:
            texts.append(text)
    return " ".join(texts).strip(": ").strip()


def _extract_from_full_text(soup, result):
    """Fallback: extract fields from the full page text."""
    all_text = soup.get_text()
    field_map = [
        ("Common name:", ["Synonymous names:", "System of medicine:", "More Information:"], "common_name"),
        ("Synonymous names:", ["System of medicine:", "More Information:"], "synonymous_names"),
        ("System of medicine:", ["More Information:"], "system_of_medicine"),
    ]
    for label, next_labels, key in field_map:
        if label not in all_text:
            continue
        start = all_text.find(label) + len(label)
        end = len(all_text)
        for nl in next_labels:
            pos = all_text.find(nl, start)
            if pos != -1 and pos < end:
                end = pos
        val = " ".join(all_text[start:end].split()).strip()
        if val and not result[key]:
            result[key] = val


# ─────────────────────────────────────────────
# Phytochemical Summary extractor
# ─────────────────────────────────────────────
def extract_phytochemical_summary(html_content):
    """
    Extract summary details from the phytochemical detailed page.
    Returns dict with identifier, name, SMILES, ClassyFire info, NP Classifier info, etc.

    Uses a full-text approach: get_text() from the summary container and then
    extract values between known label strings. This handles values inside
    <a> tags, values after <br>, and multi-line <strong> labels reliably.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    result = {
        "imppat_phytochemical_identifier": "",
        "phytochemical_name": "",
        "synonymous_chemical_names": "",
        "smiles": "",
        "classyfire_kingdom": "",
        "classyfire_superclass": "",
        "classyfire_class": "",
        "classyfire_subclass": "",
        "np_classifier_biosynthetic_pathway": "",
        "np_classifier_superclass": "",
        "np_classifier_class": "",
        "np_likeness_score": "",
    }

    # ── Phytochemical name from the page title ──
    h5 = soup.find("h5")
    if h5:
        text = h5.get_text(strip=True)
        if ":" in text:
            result["phytochemical_name"] = text.split(":", 1)[1].strip()
        else:
            result["phytochemical_name"] = text

    # ── Extract from the page using full-text parsing ──
    # Collapse ALL whitespace (including newlines) so multi-word labels like
    # "ClassyFire Superclass:" are matched as contiguous strings.
    full_text = soup.get_text(separator=" ")
    full_text = " ".join(full_text.split())  # collapse all whitespace

    # Ordered list of labels as they appear in the HTML.
    # We extract the text between consecutive labels.
    labels_in_order = [
        ("IMPPAT Phytochemical identifier:", "imppat_phytochemical_identifier"),
        ("Phytochemical name:", "phytochemical_name"),
        ("Synonymous chemical names:", "synonymous_chemical_names"),
        ("External chemical identifiers:", None),  # skip this field
        ("SMILES:", "smiles"),
        ("InChI:", None),
        ("InChIKey:", None),
        ("DeepSMILES:", None),
        ("Functional groups:", None),
        ("Scaffold Graph/Node/Bond level:", None),
        ("Scaffold Graph/Node level:", None),
        ("Scaffold Graph level:", None),
        ("ClassyFire Kingdom:", "classyfire_kingdom"),
        ("ClassyFire Superclass:", "classyfire_superclass"),
        ("ClassyFire Class:", "classyfire_class"),
        ("ClassyFire Subclass:", "classyfire_subclass"),
        ("NP Classifier Biosynthetic pathway:", "np_classifier_biosynthetic_pathway"),
        ("NP Classifier Superclass:", "np_classifier_superclass"),
        ("NP Classifier Class:", "np_classifier_class"),
        ("NP-Likeness score:", "np_likeness_score"),
    ]

    for i, (label, key) in enumerate(labels_in_order):
        if key is None:
            continue
        pos = full_text.find(label)
        if pos == -1:
            continue
        start = pos + len(label)

        # Find end: the position of the next label that actually exists in the text
        end = len(full_text)
        for j in range(i + 1, len(labels_in_order)):
            next_label = labels_in_order[j][0]
            npos = full_text.find(next_label, start)
            if npos != -1:
                end = npos
                break

        # Also look for section headings as boundaries
        for heading in ["Summary", "Chemical structure information",
                        "Chemical structure download", "Molecular scaffolds",
                        "Chemical classification"]:
            hpos = full_text.find(heading, start)
            if hpos != -1 and hpos < end:
                end = hpos

        value = full_text[start:end].strip()
        # Clean: collapse whitespace, remove stray commas at end
        value = " ".join(value.split()).strip(", ").strip()

        if value and key:
            # Don't overwrite phytochemical_name if already set from h5
            if key == "phytochemical_name" and result[key]:
                continue
            result[key] = value

    # ── IMPPAT identifier fallback: from URLs ──
    if not result["imppat_phytochemical_identifier"]:
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "/phytochemical-detailedpage/" in href:
                result["imppat_phytochemical_identifier"] = href.split("/")[-1]
                break

    return result


# ─────────────────────────────────────────────
# Property table extractor (Physicochemical / Drug-likeness / ADMET)
# ─────────────────────────────────────────────
def extract_property_table(html_content, section_heading):
    """
    Extract rows from a Property name | Tool | Property value table.
    section_heading: e.g. "Physicochemical properties", "Drug-likeness properties", "ADMET properties"
    Returns list of {"property_name": ..., "property_value": ...}
    """
    soup = BeautifulSoup(html_content, "html.parser")
    properties = []

    # Find all tables with the bordered class
    for table in soup.find_all("table", class_="table"):
        # Check if this table's section matches the heading
        # Look for the heading above the table
        parent = table.parent
        heading_found = False

        # Search upward for the section heading
        for el in table.find_all_previous(["h6", "center"]):
            if section_heading.lower() in el.get_text(strip=True).lower():
                heading_found = True
                break

        if not heading_found:
            continue

        # Verify this table has the right columns
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if "property name" not in " ".join(headers).lower():
            continue

        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                prop_name = " ".join(cols[0].get_text(strip=True).split())
                prop_value = " ".join(cols[2].get_text(strip=True).split())
                if prop_name:
                    properties.append({
                        "property_name": prop_name,
                        "property_value": prop_value,
                    })
        if properties:
            break  # Found the right table

    return properties


# ─────────────────────────────────────────────
# Chemical descriptors extractor
# ─────────────────────────────────────────────
def extract_chemical_descriptors(html_content):
    """
    Extract rows from the Chemical descriptors DataTable.
    Columns: Tool, Type, Descriptor, Description, Descriptor class, Result
    Returns list of dicts with: descriptor, description, descriptor_class, result
    """
    soup = BeautifulSoup(html_content, "html.parser")
    descriptors = []

    # Find the descriptors table - it has id="table_id" or class containing "dataTable"
    table = soup.find("table", id="table_id")
    if not table:
        table = soup.find("table", class_="dataTable")
    if not table:
        # Fallback: find the table in the descriptors section
        for t in soup.find_all("table", class_="table"):
            for el in t.find_all_previous(["h6", "center"]):
                if "chemical descriptor" in el.get_text(strip=True).lower() or "descriptor" in el.get_text(strip=True).lower():
                    table = t
                    break
            if table == t:
                break

    if not table:
        return descriptors

    rows = table.find_all("tr")
    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 6:
            descriptors.append({
                "tool": " ".join(cols[0].get_text(strip=True).split()),
                "type": " ".join(cols[1].get_text(strip=True).split()),
                "descriptor": " ".join(cols[2].get_text(strip=True).split()),
                "description": " ".join(cols[3].get_text(strip=True).split()),
                "descriptor_class": " ".join(cols[4].get_text(strip=True).split()),
                "result": " ".join(cols[5].get_text(strip=True).split()),
            })

    return descriptors


# ─────────────────────────────────────────────
# Read plant list from CSV
# ─────────────────────────────────────────────
def read_plant_csv(csv_path=CSV_FILE):
    """Read all plants from the CSV file. Returns list of {Value, Plant Name}."""
    plants = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            plants.append(row)
    return plants


def filter_plants(all_plants, target_names):
    """
    Filter the CSV plant list to include only plants whose name
    matches one of target_names (case-insensitive).
    """
    target_lower = {n.strip().lower() for n in target_names}
    return [p for p in all_plants if p["Plant Name"].strip().lower() in target_lower]


# ─────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────
def run_pipeline(plant_names):
    """
    Run the full extraction pipeline for the given list of plant names.
    """
    # Read CSV
    all_plants = read_plant_csv()
    print(f"📄 Loaded {len(all_plants)} plants from {CSV_FILE}")

    # Filter
    plants = filter_plants(all_plants, plant_names)
    if not plants:
        print("⚠ No matching plants found in CSV for the given names:")
        for n in plant_names:
            print(f"   - {n}")
        return

    print(f"🎯 Will process {len(plants)} plant(s):\n")

    for idx, plant in enumerate(plants, 1):
        plant_name = plant["Plant Name"]
        plant_url_path = plant["Value"]
        print(f"{'='*60}")
        print(f"[{idx}/{len(plants)}] 🌿 {plant_name}")
        print(f"{'='*60}")

        # Setup directories
        wp_dir, js_dir = setup_directories(plant_name)

        # ── Step 1: Download plant details page ──
        plant_url = urljoin(BASE_URL, plant_url_path)
        plant_html_path = os.path.join(wp_dir, "plant_details.html")
        print(f"  ↓ Downloading plant page...")

        plant_html = download_page(plant_url, plant_html_path)
        if not plant_html:
            print(f"  ✖ Skipping {plant_name} — failed to download plant page")
            continue
        print(f"  ✓ Saved → {plant_html_path}")

        time.sleep(REQUEST_DELAY)

        # ── Step 2: Extract plant-level data ──
        print(f"  ⚙ Extracting plant data...")
        plant_data = extract_plant_data(plant_html)
        print(f"  ✓ Found {len(plant_data['phytochemicals'])} phytochemicals")
        print(f"    Common name: {plant_data.get('common_name', 'N/A')}")
        print(f"    System of medicine: {plant_data.get('system_of_medicine', 'N/A')}")

        # ── Step 3: For each phytochemical, download & extract detail pages ──
        phyto_ids = [
            p["imppat_phytochemical_identifier"]
            for p in plant_data["phytochemicals"]
            if p.get("imppat_phytochemical_identifier")
        ]
        # Deduplicate while preserving order
        seen = set()
        unique_ids = []
        for pid in phyto_ids:
            if pid not in seen:
                seen.add(pid)
                unique_ids.append(pid)

        print(f"\n  📦 Processing {len(unique_ids)} unique phytochemical IDs...")

        phytochemical_details = {}

        for p_idx, phyto_id in enumerate(unique_ids, 1):
            print(f"\n  [{p_idx}/{len(unique_ids)}] {phyto_id}")

            detail = {"imppat_phytochemical_identifier": phyto_id}

            for page_type, url_template in PHYTO_URLS.items():
                url = urljoin(BASE_URL, url_template.format(id=phyto_id))
                filename = f"{phyto_id}_{page_type}.html"
                save_path = os.path.join(wp_dir, filename)

                print(f"    ↓ {page_type}...")
                html = download_page(url, save_path)

                if not html:
                    print(f"    ✖ Failed: {page_type}")
                    continue

                # Extract data based on page type
                if page_type == "summary":
                    summary = extract_phytochemical_summary(html)
                    detail.update(summary)

                elif page_type == "physicochemical":
                    props = extract_property_table(html, "Physicochemical properties")
                    detail["physicochemical_properties"] = props
                    print(f"      → {len(props)} properties")

                elif page_type == "drug_likeness":
                    props = extract_property_table(html, "Drug-likeness properties")
                    detail["drug_likeness_properties"] = props
                    print(f"      → {len(props)} properties")

                elif page_type == "admet":
                    props = extract_property_table(html, "ADMET properties")
                    detail["admet_properties"] = props
                    print(f"      → {len(props)} properties")

                elif page_type == "descriptors":
                    descs = extract_chemical_descriptors(html)
                    detail["chemical_descriptors"] = descs
                    print(f"      → {len(descs)} descriptors")

                time.sleep(REQUEST_DELAY)

            phytochemical_details[phyto_id] = detail

        # ── Step 4: Merge phytochemical details into plant data ──
        for phyto in plant_data["phytochemicals"]:
            pid = phyto.get("imppat_phytochemical_identifier", "")
            if pid in phytochemical_details:
                phyto["details"] = phytochemical_details[pid]

        # ── Step 5: Save complete JSON ──
        json_path = os.path.join(js_dir, "plant_data.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(plant_data, f, indent=2, ensure_ascii=False)
        print(f"\n  💾 Saved JSON → {json_path}")
        print(f"  ✅ Done: {plant_name}\n")

    print(f"\n{'='*60}")
    print(f"🎉 Pipeline complete! Processed {len(plants)} plant(s)")
    print(f"   HTML files → {WEBPAGES_DIR}/")
    print(f"   JSON files → {JSONS_DIR}/")
    print(f"{'='*60}")


# ─────────────────────────────────────────────
# Entry point — edit the plant list below
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # Add the plant names you want to extract below.
    # These must match names in plant_options.csv (case-insensitive).
    PLANTS_TO_EXTRACT = [
        "Curcuma longa",
        "Glycyrrhiza glabra",
        "Zingiber officinale",
        "Hypericum perforatum"
        # Add more plant names here...
    ]

    run_pipeline(PLANTS_TO_EXTRACT)
