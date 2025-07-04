# API-Request-Sapo-Emprego
This project provides a Python-based solution for interacting with the [SAPO Emprego API](https://emprego.sapo.pt/api/documentation/), enabling users to submit job postings programmatically. It includes tools for transforming structured job data into the required XML format and handling API requests efficiently.

## Features
- Convert structured job posting data into SAPO Emprego-compatible XML.
- Automate the submission of job postings via the SAPO Emprego API.
- Utilize customizable mappings for countries and job categories.
- Includes example payloads and mapping configurations for ease of use.

## Getting Started
### Prerequisites
- Python 3.7 or higher
- Required Python packages listed in requirements.txt

### Installation
1. Clone the repository:

```bash
git clone https://github.com/srdobolo/API-Request-Sapo-Emprego.git
cd API-Request-Sapo-Emprego
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage
1. Prepare your job posting data following the structure in payload example.json.
2. Customize mapping.json and country_mapping.py as needed to match your specific categories and country codes.
3. Run the main script to generate the XML and submit the job posting:

python main.py

## Files Overview
- [main.py](https://github.com/srdobolo/API-Request-Sapo-Emprego/blob/main/main.py): Core script for processing job data and handling API requests.
- [payload example.json](https://github.com/srdobolo/API-Request-Sapo-Emprego/blob/main/payload%20example.json): Sample JSON payload illustrating the expected job data format.
- [mapping.json](https://github.com/srdobolo/API-Request-Sapo-Emprego/blob/main/mapping.json): Defines mappings for job categories and other relevant fields.
- [country_mapping.py](https://github.com/srdobolo/API-Request-Sapo-Emprego/blob/main/country_mapping.py): Contains country code mappings to align with SAPO Emprego requirements.
- [requirements.txt](https://github.com/srdobolo/API-Request-Sapo-Emprego/blob/main/requirements.txt): Lists all Python dependencies needed for the project.

## License
This project is licensed under the MIT License.

## Contributing
Contributions are welcome! Please fork the repository and submit a pull request with your enhancements.

## Contact
For questions or support, please open an issue in the repository.

Note: This project is not officially affiliated with SAPO Emprego. For official API documentation and support, visit [SAPO Emprego API Documentation](https://emprego.sapo.pt/api/documentation/).