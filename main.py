import requests
from bs4 import BeautifulSoup
import json
import html
from datetime import datetime
from country_mapping import country_mapping

# Single job URL for debugging
JOB_URL = "https://www.recruityard.com/find-jobs-all/content-moderation-with-german-in-lisbon-pt"

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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def convert_to_plain_text(html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    output = []
    
    # Iterate through all elements in the parsed HTML
    for tag in soup.find_all(['p', 'h3', 'li']):
        if tag.name == 'p':
            # Paragraphs are added as-is with a blank line after
            output.append(tag.get_text().strip())
            output.append("")
        elif tag.name == 'h3':
            # Headers are added with a colon and a blank line after
            output.append(tag.get_text().strip())
            output.append("")
        elif tag.name == 'li':
            # Add the list item text
            output.append(tag.get_text().strip())
            # Check if this is the last <li> in its <ul> parent
            parent_ul = tag.find_parent('ul')
            if parent_ul and tag == parent_ul.find_all('li')[-1]:
                # Add an extra blank line after the last <li> in the <ul>
                output.append("")

    # Join all lines into a single string, removing extra blank lines at the end
    return "\n".join(output).rstrip()

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
        return None

def create_mapping_file(api_token):
    mappings = {}
    critical_fields = ["country_id", "district_ids", "category_ids", "schedule_type_id", "annual_salary_range_id"]
    for endpoint in ENDPOINTS:
        data = fetch_endpoint_data(endpoint, api_token)
        if data and isinstance(data, dict):
            items = data.get('data', [])
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
                mappings[endpoint] = mapping_dict
            except (KeyError, TypeError) as e:
                print(f"Error parsing {endpoint} data: {e}")
                mappings[endpoint] = {}
        else:
            print(f"Skipping {endpoint} - no valid data returned (data: {data})")
            mappings[endpoint] = {}
    try:
        with open(MAPPING_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(mappings, f, indent=2, ensure_ascii=False)
        print(f"Created {MAPPING_FILE_PATH} successfully.")
    except Exception as e:
        print(f"Error writing {MAPPING_FILE_PATH}: {e}")
        exit(1)
    return mappings

# Load API token and mappings
try:
    with open(KEY_FILE_PATH, "r") as file:
        API_TOKEN = file.read().strip()
except FileNotFoundError:
    print(f"Error: The file '{KEY_FILE_PATH}' was not found.")
    exit(1)

try:
    with open(MAPPING_FILE_PATH, 'r', encoding='utf-8') as f:
        mappings = json.load(f)
except FileNotFoundError:
    mappings = create_mapping_file(API_TOKEN)

# Fetch job page
print(f"Fetching job page: {JOB_URL}")
try:
    response = requests.get(JOB_URL, headers=HEADERS)
    response.raise_for_status()
    job_html_content = response.content
except requests.RequestException as e:
    print(f"Error fetching job URL {JOB_URL}: {e}")
    exit(1)

# Parse JSON-LD
job_soup = BeautifulSoup(job_html_content, 'html.parser')
script_tag = job_soup.find('script', type='application/ld+json')

if script_tag and script_tag.string:
    json_content = script_tag.string
    try:
        json_content_unescaped = html.unescape(json_content)
        data = json.loads(json_content_unescaped)
        print("Raw JSON-LD data:", json.dumps(data, indent=2))

        # Convert description to plain text
        plain_description = convert_to_plain_text(data.get('description', ''))

        # Extract and format dates
        start_date_raw = data.get('datePosted', datetime.now().strftime('%Y-%m-%d'))
        end_date_raw = data.get('validThrough', (datetime.now().replace(year=datetime.now().year + 1)).strftime('%Y-%m-%d'))
        # Ensure dates are in YYYY-MM-DD format
        start_date = start_date_raw.split('T')[0] if 'T' in start_date_raw else start_date_raw
        end_date = end_date_raw.split('T')[0] if 'T' in end_date_raw else end_date_raw

        region = data.get('jobLocation', {}).get('address', {}).get('addressRegion', '').lower()
        if region == 'lisbon':
            region = 'lisboa'
        
        work_model = data.get('jobLocationType', {})
        if work_model == 'TELECOMMUTE':
            work_model = 'remote'
        else:
            work_model = 'presential'

        category_ids = data.get('industry', {}).get('value', '')
        if category_ids == 'Customer Service':
            category_ids = 'call-center, helpdesk e telemarketing'
        elif category_ids == 'Healthcare':
            category_ids = 'saúde'

        schedule_type = data.get('employmentType', {})
        if schedule_type == 'FULL_TIME':
            schedule_type = 'full-time'
        elif schedule_type == 'PART_TIME':
            schedule_type = 'part-time'

        # Extract salary value
        salary_value = data.get('baseSalary', {}).get('value', {}).get('value', 'undisclosed')
        min_salary = 'undisclosed'
        max_salary = 'undisclosed'

        # Process salary if it's a string
        if isinstance(salary_value, str):
            # Handle range format like "1050 - 1300"
            if '-' in salary_value:
                salary_parts = [part.strip() for part in salary_value.split('-')]
                if len(salary_parts) == 2:
                    # Check if both parts are valid numbers
                    if (salary_parts[0].replace('.', '').isdigit() and 
                        salary_parts[1].replace('.', '').isdigit()):
                        min_salary = float(salary_parts[0])  # Convert to float
                        max_salary = float(salary_parts[1])  # Convert to float

        if isinstance(max_salary, (int, float)):
            max_annual_salary = max_salary * 12

            if max_annual_salary < 15000:
                max_annual_salary = 'até 15.000€'
            elif max_annual_salary < 25000:
                max_annual_salary = 'de 15.000€ a 25.000€'
            elif max_annual_salary < 35000:
                max_annual_salary = 'de 25.000€ a 35.000€'
            elif max_annual_salary < 50000:
                max_annual_salary = 'de 35.000€ a 50.000€'
            else:
                max_annual_salary = 'mais de 50.000€'
        else:
            max_annual_salary = 'a definir'
        
        country_id = data.get('jobLocation', {}).get('address', {}).get('addressCountry', 'PT').upper()
        country_id = country_mapping.get(country_id, country_id) 

        # Payload construction
        payload = {
            "title": data.get('title', ''),
            "offer_description": plain_description,
            "reference": data.get('identifier', {}).get('value', ''),
            "country_id": mappings.get('country_id', {}).get(country_id, country_id),
            "district_ids": [mappings.get('district_ids', {}).get(region, 0)],  # Array with mapped ID
            "work_model": work_model,
            "category_ids": [mappings.get('category_ids', {}).get(
                "call-center, helpdesk e telemarketing" if category_ids == "customer service" else category_ids, 
                category_ids
            )],  # Array with mapped ID
            "anonymous_company": False,  # Boolean value
            "schedule_type_id": mappings.get('schedule_type_id', {}).get(schedule_type.lower(), None),  # Numeric ID
            "annual_salary_range_id": mappings.get('annual_salary_range_id', {}).get(max_annual_salary.lower(), None),  # Numeric ID
            "emails_to_notify": ["info@recruityard.com"],  # Array of emails
            "start_date": start_date,
            "end_date": end_date
        }

        # Remove None values and ensure critical fields are present
        required_fields = ["country_id", "schedule_type_id", "annual_salary_range_id"]
        for field in required_fields:
            if payload.get(field) is None:
                print(f"Error: Required field '{field}' could not be mapped. Check mapping.json.")
                exit(1)

        payload = {k: v for k, v in payload.items() if v is not None}

        print("Payload to be sent:", json.dumps(payload, indent=2, ensure_ascii=False))

        # POST request
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