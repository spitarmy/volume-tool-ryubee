from pydantic import BaseModel
from typing import Any

class JobCreate(BaseModel):
    job_name: str
    customer_name: str = ""
    address: str = ""
    work_date: str | None = None
    notes: str = ""
    total_volume_m3: float | None = None
    price_total: int = 0
    status: str = "pending"
    ai_result: Any = None
    pipeline_stage: str = "inquiry"
    job_type: str = "other"
    assigned_to: str | None = None
    customer_id: str | None = None
    form_data: str | None = None

try:
    j = JobCreate(**{
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
    })
    print("Success")
except Exception as e:
    print(e)
