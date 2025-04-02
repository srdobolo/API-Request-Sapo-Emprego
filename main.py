import requests
from bs4 import BeautifulSoup
import json
import html
from datetime import datetime

# Single job URL for debugging
JOB_URL = "https://www.recruityard.com/find-jobs-all/beauty-advisor-with-german-in-porto-pt"

# API endpoints (Sandbox)
API_BASE_URL = "https://qa.services.telecom.pt/SAPOEmprego"
ENDPOINTS = {
    "available_slots_id": "/availablePositions.list",
    "category_ids": "/jobCategories.list",
    "country_id": "/countries.list",
    "district_ids": "/districts.list",
    "municipality_id": "/municipalities.list",
    "contract_type_id": "/contractTypes.list",
    "schedule_type_id": "/workHours.list",
    "min_qualifications_id": "/qualifications.list",
    "professional_experience_id": "/jobExperience.list",
    "annual_salary_range_id": "/jobSalaryRange.list"
}
OFFERS_ADD_URL = f"{API_BASE_URL}/offers.add"
KEY_FILE_PATH = "API_ACCESS_KEY"
MAPPING_FILE_PATH = "mapping.json"

# Headers with API token
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Function to convert full HTML to minimalist HTML with only <br>
def simplify_html(html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    for element in soup(['script', 'style']):
        element.decompose()
    lines = []
    for element in soup.recursiveChildGenerator():
        if isinstance(element, str):
            text = element.strip()
            if text:
                lines.append(text)
        elif element.name in ['br', 'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            lines.append('')
    result = ''
    prev_empty = False
    for line in lines:
        if line:
            result += line + '<br>'
            prev_empty = False
        elif not prev_empty:
            result += '<br>'
            prev_empty = True
    if result.endswith('<br>'):
        result = result[:-4]
    return result

# Function to fetch data from an endpoint and return it
def fetch_endpoint_data(endpoint, api_token):
    url = f"{API_BASE_URL}{ENDPOINTS[endpoint]}"
    headers = HEADERS.copy()
    headers['X-API-TOKEN'] = api_token
    print(f"Attempting to fetch {endpoint} from {url}")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        print(f"Response from {endpoint} ({url}):", json.dumps(data, indent=2))
        return data
    except requests.RequestException as e:
        print(f"Error fetching {endpoint} from {url}: {e}")
        if 'response' in locals():
            print(f"Response status: {response.status_code}, content: {response.text}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {endpoint}: {e}")
        return None

# Function to create mapping.json from endpoint data
def create_mapping_file(api_token):
    mappings = {}
    critical_fields = ["country_id", "district_ids", "category_ids", "schedule_type_id", "annual_salary_range_id"]
    
    for endpoint in ENDPOINTS:
        data = fetch_endpoint_data(endpoint, api_token)
        # Handle both {"total": N, "data": [...]} and {"data": [...]} structures
        if data and isinstance(data, dict):
            items = data.get('data', [])  # Default to empty list if 'data' is missing
            if not isinstance(items, list):
                print(f"Skipping {endpoint} - 'data' is not a list: {items}")
                mappings[endpoint] = {}
                continue
            try:
                mapping_dict = {}
                for item in items:
                    if 'id' not in item:
                        print(f"Warning: Item in {endpoint} lacks 'id': {item}")
                        continue
                    # Expanded key fallback chain to match all known fields
                    key = (item.get('code') or 
                           item.get('name') or 
                           item.get('description') or 
                           item.get('pay_range') or 
                           item.get('experience') or 
                           item.get('qualification') or 
                           item.get('work_hours') or 
                           item.get('contract_type') or 
                           item.get('municipality') or 
                           item.get('district') or 
                           item.get('country') or 
                           item.get('category') or 
                           item.get('position') or 
                           str(item.get('id'))).lower()
                    if not key:
                        print(f"Warning: No valid key found for item in {endpoint}: {item}")
                        continue
                    mapping_dict[key] = item['id']
                    print(f"Debug: {endpoint} mapped '{key}' to {item['id']}")
                mappings[endpoint] = mapping_dict
                if not mapping_dict:
                    print(f"Warning: No valid mappings found for {endpoint} (empty or no valid items)")
            except (KeyError, TypeError) as e:
                print(f"Error parsing {endpoint} data: {e}")
                mappings[endpoint] = {}
        else:
            print(f"Skipping {endpoint} - no valid data returned (data: {data})")
            mappings[endpoint] = {}

    # Log the mappings before saving
    print("Generated mappings:", json.dumps(mappings, indent=2))

    # Check for critical empty mappings, but proceed with warnings
    missing_critical = [field for field in critical_fields if not mappings.get(field)]
    if missing_critical:
        print(f"Warning: Critical fields {missing_critical} are empty in mappings. Using fallbacks.")

    # Save to mapping.json even if empty
    try:
        with open(MAPPING_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(mappings, f, indent=2, ensure_ascii=False)
        print(f"Created {MAPPING_FILE_PATH} successfully.")
    except Exception as e:
        print(f"Error writing {MAPPING_FILE_PATH}: {e}")
        exit(1)

    return mappings

# Read the API token
try:
    with open(KEY_FILE_PATH, "r") as file:
        API_TOKEN = file.read().strip()
except FileNotFoundError:
    print(f"Error: The file '{KEY_FILE_PATH}' was not found. Please ensure it exists.")
    exit(1)

# Create or update mapping.json
mappings = create_mapping_file(API_TOKEN)

# Fetch the job page
print(f"Fetching job page: {JOB_URL}")
try:
    response = requests.get(JOB_URL, headers=HEADERS)
    response.raise_for_status()
    job_html_content = response.content
except requests.RequestException as e:
    print(f"Error fetching job URL {JOB_URL}: {e}")
    exit(1)

# Parse the job page
job_soup = BeautifulSoup(job_html_content, 'html.parser')
script_tag = job_soup.find('script', type='application/ld+json')

if script_tag and script_tag.string:
    json_content = script_tag.string
    try:
        json_content_unescaped = html.unescape(json_content)
        data = json.loads(json_content_unescaped)

        # Debug: Print raw JSON data
        print("Raw JSON data:", json.dumps(data, indent=2))

        # Simplify the HTML description
        minimalist_description = simplify_html(data.get('description', ''))

        # Map data to SAPO Emprego fields using fetched mappings with fallbacks
        payload = {
            "title": data.get('title', 'Undisclosed Job Title'),
            "offer_description": minimalist_description,
            "description": (
                f"<a href=\"{JOB_URL}?id={data.get('identifier', {}).get('value', 'job001')}&utm_source=SAPO_Emprego\" target=\"_blank\">Clique aqui para se candidatar!</a><br>"
                f"ou por email para info@recruityard.com"
            ),
            "reference": data.get('identifier', {}).get('value', 'job001'),
            "country_id": mappings.get('country_id', {}).get('portugal', 620),
            "district_ids": [mappings.get('district_ids', {}).get('porto', 13)],
            "location": data.get('jobLocation', {}).get('address', {}).get('addressLocality', 'Porto'),
            "employment_type": data.get('employmentType', 'FULL_TIME'),
            "category_ids": [mappings.get('category_ids', {}).get('customer service', 9)],  # Assuming 'Call-Center' fits
            "anonymous_company": False,
            "schedule_type_id": mappings.get('schedule_type_id', {}).get('full-time', 1),
            "annual_salary_range_id": mappings.get('annual_salary_range_id', {}).get('1084 - 1448', 2),
            "emails_to_notify": ["info@recruityard.com"],
            "start_date": data.get('datePosted', datetime.now().strftime('%Y-%m-%d')),
            "end_date": data.get('validThrough', (datetime.now().replace(year=datetime.now().year + 1)).strftime('%Y-%m-%d'))
        }

        # Remove None values from payload
        payload = {k: v for k, v in payload.items() if v is not None}

        # Debug: Print the payload
        print("Payload to be sent:", json.dumps(payload, indent=2, ensure_ascii=False))

        # POST request to SAPO Emprego API
        HEADERS['X-API-TOKEN'] = API_TOKEN
        post_response = requests.post(OFFERS_ADD_URL, json=payload, headers=HEADERS)
        if post_response.status_code in (200, 201):
            print(f"Job '{payload['title']}' successfully sent.")
        elif post_response.status_code == 429:
            print(f"Throttle limit reached. Status: 429. Please wait before retrying.")
        else:
            print(f"Failed to send job '{payload['title']}'. HTTP Status: {post_response.status_code}")
            print("Response Content:", post_response.text)

    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from the script tag at {JOB_URL}.")
    except Exception as e:
        print(f"Unexpected error processing job at {JOB_URL}: {e}")
else:
    print(f"No JSON script tag found at {JOB_URL}.")