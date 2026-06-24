import os
import json
import weasyprint
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader

from app.database import get_db
from app.auth import get_current_user
from app.models import User, CustomerContract, Customer, CompanySettings
from datetime import datetime

router = APIRouter(prefix="/v1/customers", tags=["Contract PDF"])

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
UPLOADS_DIR = "uploads/contracts"
os.makedirs(UPLOADS_DIR, exist_ok=True)

env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

@router.post("/{cid}/contracts/{contract_id}/generate-pdf")
def generate_contract_pdf(
    cid: str, 
    contract_id: str, 
    request: Request,
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    contract = db.query(CustomerContract).filter(
        CustomerContract.id == contract_id,
        CustomerContract.customer_id == cid,
        CustomerContract.company_id == current_user.company_id
    ).first()
    
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    customer = db.query(Customer).filter(Customer.id == cid).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Load form_data if available
    form_data = {}
    try:
        if customer.form_data:
            form_data = json.loads(customer.form_data)
    except:
        pass

    # Load pricing data
    pricing_list = []
    try:
        if contract.pricing_data:
            pricing_list = json.loads(contract.pricing_data)
    except:
        pass
        
    # If pricing_list is empty, use the contract's unit_price and waste_type as a fallback
    if not pricing_list and contract.waste_type:
        pricing_list = [{
            "item": contract.waste_type,
            "qty": form_data.get("average_volume", "都度協議"),
            "price": contract.unit_price or 0,
            "unit": contract.unit or "kg"
        }]

    cClosing = f"{customer.billing_closing_day}日" if customer.billing_closing_day != 31 else "末日"
    cPaymentDay = f"{customer.payment_due_day}日" if customer.payment_due_day != 31 else "末日"
    
    offsets = {0: "当月", 1: "翌月", 2: "翌々月"}
    cPaymentOffset = offsets.get(customer.payment_due_month_offset, "翌月")

    start_date_raw = form_data.get("collection_start_date") or contract.contract_date
    if start_date_raw:
        try:
            dt = datetime.strptime(start_date_raw, "%Y-%m-%d")
            cStartDate = f"{dt.year}年{dt.month}月{dt.day}日"
        except:
            cStartDate = start_date_raw
    else:
        cStartDate = "契約締結日"

    context = {
        "cName": customer.name,
        "cBranchName": form_data.get("branch_name") or customer.name,
        "cBranchAddress": form_data.get("branch_address") or customer.address or "ー",
        "cStartDate": cStartDate,
        "cClosing": cClosing,
        "cPaymentOffset": cPaymentOffset,
        "cPaymentDay": cPaymentDay,
        "cPaymentMethod": form_data.get("payment_method") or "振込",
        "cNotes": contract.notes or customer.notes or "特段の定めなし",
        "cAddress": form_data.get("billing_address") or customer.address or " ",
        "cContactPerson": customer.contact_person or "                     ",
        "cPhone": customer.phone or "                     ",
        "pricing_list": pricing_list
    }

    template = env.get_template("contract_template.html")
    html_content = template.render(**context)

    # WeasyPrint needs a base URL to resolve local files like fonts
    base_url = f"file://{os.path.abspath(TEMPLATE_DIR)}/"
    
    pdf_filename = f"contract_{contract_id}_{uuid.uuid4().hex[:8]}.pdf"
    pdf_path = os.path.join(UPLOADS_DIR, pdf_filename)
    
    try:
        weasyprint.HTML(string=html_content, base_url=base_url).write_pdf(pdf_path)
    except Exception as e:
        print("WeasyPrint error:", e)
        raise HTTPException(status_code=500, detail="Failed to generate PDF")

    pdf_url = f"/uploads/contracts/{pdf_filename}"
    
    contract.contract_pdf_url = pdf_url
    db.commit()
    db.refresh(contract)

    return {"message": "PDF generated", "pdf_url": pdf_url}


@router.post("/{cid}/contracts/{contract_id}/upload-pdf")
def upload_contract_pdf(
    cid: str,
    contract_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    contract = db.query(CustomerContract).filter(
        CustomerContract.id == contract_id,
        CustomerContract.customer_id == cid,
        CustomerContract.company_id == current_user.company_id
    ).first()
    
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".pdf", ".jpg", ".jpeg", ".png"]:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    filename = f"signed_contract_{contract_id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(UPLOADS_DIR, filename)

    try:
        with open(filepath, "wb") as buffer:
            buffer.write(file.file.read())
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to upload file")

    pdf_url = f"/uploads/contracts/{filename}"
    contract.contract_pdf_url = pdf_url
    contract.status = "completed"  # Uploading signed means completed usually
    db.commit()
    db.refresh(contract)

    return {"message": "File uploaded", "pdf_url": pdf_url}


@router.get("/{cid}/contracts/{contract_id}/pdf")
def download_contract_pdf(
    cid: str,
    contract_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    contract = db.query(CustomerContract).filter(
        CustomerContract.id == contract_id,
        CustomerContract.customer_id == cid,
        CustomerContract.company_id == current_user.company_id
    ).first()
    
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
        
    if not contract.contract_pdf_url:
        raise HTTPException(status_code=404, detail="No PDF generated for this contract")

    # `contract_pdf_url` is like `/uploads/contracts/xxx.pdf`
    filepath = os.path.join("uploads", "contracts", os.path.basename(contract.contract_pdf_url))
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(filepath, media_type="application/pdf", filename=f"contract_{contract_id}.pdf")
