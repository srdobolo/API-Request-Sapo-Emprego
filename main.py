import requests
from bs4 import BeautifulSoup
import json
import html
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from country_mapping import country_mapping

# Base URL for the find-jobs section
BASE_URL = 'https://www.recruityard.com/find-jobs-all/'

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

# Set up a session with retry logic
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

successful_submissions = 0
failed_submissions = []

def convert_to_plain_text(html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    output = []
    for tag in soup.find_all(['p', 'h3', 'li']):
        if tag.name == 'p':
            output.append(tag.get_text().strip())
            output.append("")
        elif tag.name == 'h3':
            output.append(tag.get_text().strip())
            output.append("")
        elif tag.name == 'li':
            output.append(tag.get_text().strip())
            parent_ul = tag.find_parent('ul')
            if parent_ul and tag == parent_ul.find_all('li')[-1]:
                output.append("")
    return "\n".join(output).rstrip()

def fetch_endpoint_data(endpoint, api_token):
    url = f"{API_BASE_URL}{ENDPOINTS[endpoint]}"
    headers = HEADERS.copy()
    headers['X-API-TOKEN'] = api_token
    print(f"Attempting to fetch {endpoint} from {url}")
    try:
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"Response from {endpoint}:", json.dumps(data, indent=2))
        return data
    except requests.RequestException as e:
        print(f"Error fetching {endpoint} from {url}: {e}")
        return None

def create_mapping_file(api_token):
    mappings = {}
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

def clean_url(base, href):
    full_url = urljoin(base, href)
    parsed = urlparse(full_url)
    path_segments = parsed.path.split('/')
    cleaned_path = '/'.join([seg for i, seg in enumerate(path_segments) if seg != 'find-jobs-all' or i == path_segments.index('find-jobs-all')])
    return urlunparse((parsed.scheme, parsed.netloc, cleaned_path, parsed.params, parsed.query, parsed.fragment))

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

# Step 1: Fetch the main jobs page to find all job links
try:
    print(f"Fetching base URL: {BASE_URL}")
    response = session.get(BASE_URL, headers=HEADERS, timeout=10)
    response.raise_for_status()
    html_content = response.content
except requests.RequestException as e:
    print(f"Error fetching base URL: {e}")
    exit(1)

# Step 2: Parse the HTML to find all job links
soup = BeautifulSoup(html_content, 'html.parser')
job_links = list(set([
    clean_url(BASE_URL, a['href']) for a in soup.find_all('a', href=True)
    if '/find-jobs-all/' in a['href'] and a['href'].endswith('pt')
]))
print(f"Found {len(job_links)} job(s) to process: {job_links}")

# Step 3: Process each job link
for job_url in job_links:
    print(f"\nFetching job page: {job_url}")
    try:
        response = session.get(job_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        job_html_content = response.content
    except requests.RequestException as e:
        print(f"Error fetching job URL {job_url}: {e}")
        failed_submissions.append((job_url, "Unknown", str(e)))
        continue

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

            category_ids = data.get('industry', {}).get('value', '').lower()
            if category_ids == 'customer service':
                category_ids = 'call-center, helpdesk e telemarketing'
            elif category_ids == 'healthcare':
                category_ids = 'saúde'

            schedule_type = data.get('employmentType', {}).lower()
            if schedule_type == 'full_time':
                schedule_type = 'full-time'
            elif schedule_type == 'part_time':
                schedule_type = 'part-time'

            # Extract salary value
            salary_value = data.get('baseSalary', {}).get('value', {}).get('value', 'undisclosed')
            min_salary = 'undisclosed'
            max_salary = 'undisclosed'

            if isinstance(salary_value, str):
                if '-' in salary_value:
                    salary_parts = [part.strip() for part in salary_value.split('-')]
                    if len(salary_parts) == 2:
                        if (salary_parts[0].replace('.', '').isdigit() and 
                            salary_parts[1].replace('.', '').isdigit()):
                            min_salary = float(salary_parts[0])
                            max_salary = float(salary_parts[1])

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
                "country_id": mappings.get('country_id', {}).get(country_id.lower(), country_id),
                "district_ids": [mappings.get('district_ids', {}).get(region, 0)],
                "work_model": work_model,
                "category_ids": [mappings.get('category_ids', {}).get(category_ids, 0)],
                "anonymous_company": False,
                "schedule_type_id": mappings.get('schedule_type_id', {}).get(schedule_type, None),
                "annual_salary_range_id": mappings.get('annual_salary_range_id', {}).get(max_annual_salary.lower(), None),
                "emails_to_notify": ["info@recruityard.com"],
                "start_date": start_date,
                "end_date": end_date
            }

            # Remove None values and validate required fields
            required_fields = ["country_id", "schedule_type_id", "annual_salary_range_id"]
            missing_fields = [field for field in required_fields if payload.get(field) is None]
            if missing_fields:
                print(f"Error: Required field(s) {missing_fields} could not be mapped for {job_url}.")
                failed_submissions.append((job_url, payload.get('reference', 'Unknown'), f"Missing fields: {missing_fields}"))
                continue

            payload = {k: v for k, v in payload.items() if v is not None}

            print("Payload to be sent:", json.dumps(payload, indent=2, ensure_ascii=False))

            # POST request with retry
            HEADERS['X-API-TOKEN'] = API_TOKEN
            for attempt in range(3):
                try:
                    post_response = session.post(OFFERS_ADD_URL, json=payload, headers=HEADERS, timeout=10)
                    if post_response.status_code in (200, 201):
                        print(f"Job '{payload['title']}' successfully sent.")
                        successful_submissions += 1
                        break
                    elif post_response.status_code == 429:
                        print(f"Attempt {attempt + 1}: Throttle limit reached. Status: 429.")
                        if attempt < 2:
                            time.sleep(2 ** (attempt + 1))
                    else:
                        print(f"Attempt {attempt + 1}: Failed to send job '{payload['title']}'. HTTP Status: {post_response.status_code}")
                        print("Response Content:", post_response.text)
                        if attempt < 2:
                            time.sleep(2)
                except requests.RequestException as e:
                    print(f"Attempt {attempt + 1}: Error sending job '{payload['title']}': {e}")
                    if attempt < 2:
                        time.sleep(2)
            else:
                print(f"Failed to send job '{payload['title']}' after 3 attempts.")
                failed_submissions.append((job_url, payload.get('reference', 'Unknown'), post_response.text if 'post_response' in locals() else "Unknown error"))

        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from the script tag at {job_url}.")
            failed_submissions.append((job_url, "Unknown", "JSON decode error"))
        except Exception as e:
            print(f"Unexpected error processing job at {job_url}: {e}")
            failed_submissions.append((job_url, "Unknown", str(e)))
    else:
        print(f"No JSON script tag found at {job_url}.")
        failed_submissions.append((job_url, "Unknown", "No JSON data"))

    time.sleep(1)  # Delay between job requests

print("\nProcessing complete.")
print(f"Total jobs successfully submitted: {successful_submissions}/{len(job_links)}")
if failed_submissions:
    print("\nFailed submissions:")
    for url, ref, reason in failed_submissions:
        print(f"- {ref} ({url}): {reason}")