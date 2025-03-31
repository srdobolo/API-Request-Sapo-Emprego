import requests
from bs4 import BeautifulSoup
import json
import html
from urllib.parse import urljoin, urlparse, urlunparse

# Base URL for the find-jobs section
BASE_URL = 'https://www.recruityard.com/find-jobs-all/'

# API endpoint and key
API_URL = "http://partner.net-empregos.com/hrsmart_insert.asp"
REMOVE_API_URL = "http://partner.net-empregos.com/hrsmart_remove.asp"
KEY_FILE_PATH = "API_ACCESS_KEY"
MAPPING_FILE_PATH = "mapping.json"

# Headers to mimic a browser request
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

# Counter for successful job requests
successful_requests = 0

# Function to clean URLs and avoid duplicate segments
def clean_url(base, href):
    full_url = urljoin(base, href)
    parsed = urlparse(full_url)
    path_segments = parsed.path.split('/')
    cleaned_path = '/'.join([seg for i, seg in enumerate(path_segments) if seg != 'find-jobs-all' or i == path_segments.index('find-jobs-all')])
    return urlunparse((parsed.scheme, parsed.netloc, cleaned_path, parsed.params, parsed.query, parsed.fragment))

# Function to convert full HTML to minimalist HTML with only <br>
def simplify_html(html_text):
    # Parse HTML content
    soup = BeautifulSoup(html_text, 'html.parser')
    
    # Remove script and style elements
    for element in soup(['script', 'style']):
        element.decompose()
    
    # Get text with breaks
    lines = []
    for element in soup.recursiveChildGenerator():
        if isinstance(element, str):
            text = element.strip()
            if text:
                lines.append(text)
        elif element.name in ['br', 'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            lines.append('')  # Add empty line for block elements
    
    # Join lines with <br> tags, skipping consecutive empty lines
    result = ''
    prev_empty = False
    for line in lines:
        if line:
            result += line + '<br>'
            prev_empty = False
        elif not prev_empty:
            result += '<br>'
            prev_empty = True
    
    # Remove trailing <br> if present
    if result.endswith('<br>'):
        result = result[:-4]
    
    return result

# Read the API key
try:
    with open(KEY_FILE_PATH, "r") as file:
        API_KEY = file.read().strip()
except FileNotFoundError:
    print(f"Error: The file '{KEY_FILE_PATH}' was not found. Please ensure it exists.")
    exit(1)

# Load the mapping file
try:
    with open(MAPPING_FILE_PATH, "r", encoding="iso-8859-1") as file:
        mappings = json.load(file)
except FileNotFoundError:
    print(f"Error: The file '{MAPPING_FILE_PATH}' was not found. Please ensure it exists.")
    exit(1)
except json.JSONDecodeError as e:
    print(f"Error: Failed to parse '{MAPPING_FILE_PATH}': {e}")
    exit(1)

# Step 1: Load the main jobs page to find all job links
try:
    print(f"Fetching base URL: {BASE_URL}")
    response = requests.get(BASE_URL, headers=HEADERS)
    response.raise_for_status()
    html_content = response.content
except requests.RequestException as e:
    print(f"Error fetching base URL: {e}")
    exit(1)

# Step 2: Parse the HTML with BeautifulSoup to find all job links
soup = BeautifulSoup(html_content, 'html.parser')

# Debug: Print all hrefs for inspection
all_hrefs = [a['href'] for a in soup.find_all('a', href=True)]
print("All hrefs on page:", all_hrefs)

# Extract job links, deduplicate, and filter those ending with "pt"
job_links = list(set([
    clean_url(BASE_URL, a['href']) for a in soup.find_all('a', href=True)
    if '/find-jobs-all/' in a['href'] and a['href'].endswith('pt')
]))

print(f"Found {len(job_links)} job(s) to process ending with 'pt': {job_links}")

# Step 3: Process each job link
for job_url in job_links:
    print(f"Fetching job page: {job_url}")
    try:
        response = requests.get(job_url, headers=HEADERS)
        response.raise_for_status()
        job_html_content = response.content

        job_soup = BeautifulSoup(job_html_content, 'html.parser')
        script_tag = job_soup.find('script', type='application/ld+json')

        if script_tag and script_tag.string:
            json_content = script_tag.string

            try:
                json_content_unescaped = html.unescape(json_content)
                data = json.loads(json_content_unescaped)

                formatted_description, zona, categoria, tipo = clean_job_data(data, mappings)
                
                # Simplify the HTML description
                minimalist_description = simplify_html(formatted_description)

                payload = {
                    "ACCESS": API_KEY,
                    "REF": data.get('identifier', {}).get('value', 'job001'),
                    "TITULO": data.get('title', 'undisclosed'),
                    "TEXTO": (
                        f"{minimalist_description}<br><br>" +
                        f"<a href=\"{job_url}?id={data.get('identifier', {}).get('value', 'job001')}&utm_source=NET_EMPREGOS\" target=\"_blank\">Clique aqui para se candidatar!</a><br>" +
                        f"ou por email para info@recruityard.com"
                    ),
                    "ZONA": zona,
                    "CATEGORIA": categoria,
                    "TIPO": tipo,
                }

                encoded_payload = {
                    key: (value.encode('iso-8859-1', errors='replace') if isinstance(value, str) else value)
                    for key, value in payload.items()
                }

                remove_payload = {
                    "ACCESS": API_KEY,
                    "REF": data.get('identifier', {}).get('value', 'job001'),
                }

                try:
                    remove_response = requests.get(REMOVE_API_URL, params=remove_payload)
                    if remove_response.status_code == 200:
                        print(f"Job '{remove_payload['REF']}' successfully removed.")
                    else:
                        print(f"Failed to remove job '{remove_payload['REF']}'. HTTP Status: {remove_response.status_code}")
                        print("Response Content:", remove_response.text)
                except requests.RequestException as e:
                    print(f"Error removing job '{remove_payload['REF']}': {e}")
                    continue

                post_response = requests.post(API_URL, data=encoded_payload)
                if post_response.status_code == 200:
                    print(f"Job '{payload['TITULO']}' successfully sent.")
                    successful_requests += 1
                else:
                    print(f"Failed to send job '{payload['TITULO']}'. HTTP Status: {post_response.status_code}")
                    print("Response Content:", post_response.text)

            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON from the script tag at {job_url}.")
            except Exception as e:
                print(f"Unexpected error processing job at {job_url}: {e}")
        else:
            print(f"No JSON script tag found at {job_url}.")

    except requests.RequestException as e:
        print(f"Error fetching job URL {job_url}: {e}")

print("Processing complete.")
print(f"Total number of job requests successfully sent: {successful_requests}")