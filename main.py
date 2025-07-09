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
import os
from dotenv import load_dotenv

load_dotenv()

# Base URL for the find-jobs section
BASE_URL = 'https://www.recruityard.com/find-jobs-all/'

# API endpoints (Production)
API_BASE_URL = "https://services.sapo.pt/SAPOEmprego"
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
KEY_FILE_PATH = os.getenv("API_ACCESS_KEY")
if not KEY_FILE_PATH:
    print("Error: API_ACCESS_KEY is not set in the environment or .env file.")
    exit(1)
MAPPING_FILE_PATH = "mapping.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Set up a session with retry logic
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504]  # Exclude 429; handle manually
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

successful_submissions = 0
failed_submissions = []
retry_queue = []

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
        return response.json()
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
                mappings[endpoint] = {}
                continue
            mapping_dict = {}
            for item in items:
                if 'id' not in item:
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
                    continue
                mapping_dict[key] = item['id']
            mappings[endpoint] = mapping_dict
        else:
            mappings[endpoint] = {}
    with open(MAPPING_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(mappings, f, indent=2, ensure_ascii=False)
    print(f"Created {MAPPING_FILE_PATH} successfully.")
    return mappings

def clean_url(base, href):
    full_url = urljoin(base, href)
    parsed = urlparse(full_url)
    path_segments = parsed.path.split('/')
    cleaned_path = '/'.join([seg for i, seg in enumerate(path_segments) if seg != 'find-jobs-all' or i == path_segments.index('find-jobs-all')])
    return urlunparse((parsed.scheme, parsed.netloc, cleaned_path, parsed.params, parsed.query, parsed.fragment))

def process_job(job_url, mappings, api_token):
    global successful_submissions, failed_submissions, retry_queue
    print(f"\nFetching job page: {job_url}")
    try:
        response = session.get(job_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        job_html_content = response.content
    except requests.RequestException as e:
        failed_submissions.append((job_url, "Unknown", str(e)))
        return

    job_soup = BeautifulSoup(job_html_content, 'html.parser')
    script_tag = job_soup.find('script', type='application/ld+json')

    if not script_tag or not script_tag.string:
        failed_submissions.append((job_url, "Unknown", "No JSON data"))
        return

    try:
        json_content_unescaped = html.unescape(script_tag.string)
        data = json.loads(json_content_unescaped)

        plain_description = convert_to_plain_text(data.get('description', ''))
        start_date_raw = datetime.now().strftime('%Y-%m-%d')
        end_date_raw = (datetime.now().replace(month=datetime.now().month + 1)).strftime('%Y-%m-%d')
        start_date = start_date_raw.split('T')[0] if 'T' in start_date_raw else start_date_raw
        end_date = end_date_raw.split('T')[0] if 'T' in end_date_raw else end_date_raw

        region = data.get('jobLocation', {}).get('address', {}).get('addressRegion', '').lower()
        if region == 'lisbon':
            region = 'lisboa'

        work_model = 'remote' if data.get('jobLocationType', '') == 'TELECOMMUTE' else 'presential'
        category_ids = data.get('industry', {}).get('value', '').lower()
        if category_ids == 'customer service':
            category_ids = 'call-center, helpdesk e telemarketing'
        elif category_ids == 'healthcare':
            category_ids = 'saúde'

        schedule_type = data.get('employmentType', '').lower()
        if schedule_type == 'full_time':
            schedule_type = 'full-time'
        elif schedule_type == 'part_time':
            schedule_type = 'part-time'

        salary_value = data.get('baseSalary', {}).get('value', {}).get('value', 'undisclosed')
        min_salary = max_salary = 'undisclosed'
        if isinstance(salary_value, str) and '-' in salary_value:
            salary_parts = [part.strip() for part in salary_value.split('-')]
            if len(salary_parts) == 2 and all(part.replace('.', '').isdigit() for part in salary_parts):
                min_salary, max_salary = float(salary_parts[0]), float(salary_parts[1])

        max_annual_salary = 'a definir'
        if isinstance(max_salary, (int, float)):
            max_annual_salary_value = max_salary * 12
            if max_annual_salary_value < 15000:
                max_annual_salary = 'até 15.000€'
            elif max_annual_salary_value < 25000:
                max_annual_salary = 'de 15.000€ a 25.000€'
            elif max_annual_salary_value < 35000:
                max_annual_salary = 'de 25.000€ a 35.000€'
            elif max_annual_salary_value < 50000:
                max_annual_salary = 'de 35.000€ a 50.000€'
            else:
                max_annual_salary = 'mais de 50.000€'

        country_id = country_mapping.get(data.get('jobLocation', {}).get('address', {}).get('addressCountry', 'PT').upper(), 'PT')

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
            "emails_to_notify": ["info@recruityard.com", "resumes@recruityard.zohorecruitmail.eu", "joao@recruityard.com"],
            "start_date": start_date,
            "end_date": end_date
        }

        required_fields = ["country_id", "schedule_type_id", "annual_salary_range_id"]
        missing_fields = [field for field in required_fields if payload.get(field) is None]
        if missing_fields:
            failed_submissions.append((job_url, payload.get('reference', 'Unknown'), f"Missing fields: {missing_fields}"))
            return

        payload = {k: v for k, v in payload.items() if v is not None}

        HEADERS['X-API-TOKEN'] = api_token
        for attempt in range(3):
            try:
                post_response = session.post(OFFERS_ADD_URL, json=payload, headers=HEADERS, timeout=10)
                if post_response.status_code in (200, 201):
                    print(f"Job '{payload['title']}' successfully sent.")
                    successful_submissions += 1
                    return
                elif post_response.status_code == 429:
                    print(f"Attempt {attempt + 1}: Rate limit hit (429). Adding to retry queue.")
                    if attempt == 2:  # Only queue on final attempt
                        retry_queue.append((job_url, payload))
                    time.sleep(10)  # Short wait before retrying within loop
                else:
                    print(f"Attempt {attempt + 1}: Failed with status {post_response.status_code}: {post_response.text}")
                    if attempt < 2:
                        time.sleep(2 ** (attempt + 1))
            except requests.RequestException as e:
                print(f"Attempt {attempt + 1}: Error: {e}")
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
        else:
            failed_submissions.append((job_url, payload.get('reference', 'Unknown'), post_response.text if 'post_response' in locals() else "Unknown error"))

    except json.JSONDecodeError:
        failed_submissions.append((job_url, "Unknown", "JSON decode error"))
    except Exception as e:
        failed_submissions.append((job_url, "Unknown", str(e)))

try:
    with open(MAPPING_FILE_PATH, 'r', encoding='utf-8') as f:
        mappings = json.load(f)
except FileNotFoundError:
    mappings = create_mapping_file(KEY_FILE_PATH)

# Fetch job links
try:
    print(f"Fetching base URL: {BASE_URL}")
    response = session.get(BASE_URL, headers=HEADERS, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    job_links = list(set([clean_url(BASE_URL, a['href']) for a in soup.find_all('a', href=True) if '/find-jobs-all/' in a['href'] and a['href'].endswith('pt')]))
    print(f"Found {len(job_links)} job(s) to process: {job_links}")
except requests.RequestException as e:
    print(f"Error fetching base URL: {e}")
    exit(1)

# Process jobs with rate limiting (15 requests per minute = 4 seconds per request)
for job_url in job_links:
    process_job(job_url, mappings, KEY_FILE_PATH)
    time.sleep(5)  # Enforce 15 requests per minute

# Retry failed jobs due to rate limiting
if retry_queue:
    print("\nRetrying jobs that hit rate limit after a 60-second delay...")
    time.sleep(60)  # Wait a full minute to reset the rate limit
    for job_url, payload in retry_queue[:]:
        print(f"\nRetrying: {job_url}")
        HEADERS['X-API-TOKEN'] = KEY_FILE_PATH
        try:
            post_response = session.post(OFFERS_ADD_URL, json=payload, headers=HEADERS, timeout=10)
            if post_response.status_code in (200, 201):
                print(f"Job '{payload['title']}' successfully sent on retry.")
                successful_submissions += 1
                retry_queue.remove((job_url, payload))
            elif post_response.status_code == 429:
                print(f"Still rate limited (429). Keeping in queue for manual retry later.")
            else:
                failed_submissions.append((job_url, payload.get('reference', 'Unknown'), post_response.text))
                retry_queue.remove((job_url, payload))
        except requests.RequestException as e:
            failed_submissions.append((job_url, payload.get('reference', 'Unknown'), str(e)))
            retry_queue.remove((job_url, payload))
        time.sleep(5)  # Maintain rate limit during retries

print("\nProcessing complete.")
print(f"Total jobs successfully submitted: {successful_submissions}/{len(job_links)}")
if failed_submissions:
    print("\nFailed submissions:")
    for url, ref, reason in failed_submissions:
        print(f"- {ref} ({url}): {reason}")
if retry_queue:
    print("\nJobs still in retry queue (unresolved rate limits):")
    for job_url, payload in retry_queue:
        print(f"- {payload.get('reference', 'Unknown')} ({job_url})")