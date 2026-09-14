import requests
import json

url = "https://ryubee-api-v2.onrender.com/v1/jobs"
headers = {"Content-Type": "application/json"}
payload = {
    "status": "estimated",
    "pipeline_stage": "inquiry",
    "job_type": "general_waste",
    "job_name": "",
    "customer_id": None,
    "customer_name": "",
    "address": "",
    "work_date": "",
    "work_time": "",
    "price_total": None,
    "workers": None,
    "total_volume_m3": None,
    "notes": "",
    "form_data": "{}"
}

response = requests.post(url, headers=headers, json=payload)
print(response.status_code)
print(response.text)
