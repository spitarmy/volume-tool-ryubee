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
from app.models import User, CustomerContract, Customer, CompanySettings, DisposalCompanyMaster
from datetime import datetime, timedelta

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
    startYear, startMonth, startDay = "  ", "  ", "  "
    endYear, endMonth, endDay = "  ", "  ", "  "
    
    now = datetime.now()
    currentYearReiwa = now.year - 2018
    currentMonth = now.month
    currentDay = now.day

    if start_date_raw:
        try:
            dt = datetime.strptime(start_date_raw, "%Y-%m-%d")
        except:
            dt = now
    else:
        dt = now

    cStartDate = f"{dt.year}年{dt.month}月{dt.day}日"
    startYear, startMonth, startDay = dt.year, dt.month, dt.day
    end_dt = dt + timedelta(days=364)
    endYear, endMonth, endDay = end_dt.year, end_dt.month, end_dt.day

    disposalCompany = contract.disposal_company or "（処分業者未設定）"

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
        "pricing_list": pricing_list,
        "startYear": startYear,
        "startMonth": startMonth,
        "startDay": startDay,
        "endYear": endYear,
        "endMonth": endMonth,
        "endDay": endDay,
        "disposalCompany": disposalCompany,
        "currentYearReiwa": currentYearReiwa,
        "currentMonth": currentMonth,
        "currentDay": currentDay
    }

    disposal_company_str = contract.disposal_company or ""
    
    if "旭興" in disposal_company_str:
        html1 = env.get_template("template_yamabun_collection.html").render(**context)
        html2 = env.get_template("template_kyokko_disposal.html").render(**context)
        html_content = html1 + '<div style="page-break-before: always;"></div>' + html2
    elif "HIRAYAMA" in disposal_company_str:
        template = env.get_template("template_hirayama.html")
        html_content = template.render(**context)
    else:
        template = env.get_template("template_yamabun_collection.html")
        html_content = template.render(**context)

    # 処分業者マスターからの情報取得（別紙と許可証用）
    active_contractors = form_data.get("active_contractors", [])
    if active_contractors:
        disposal_masters = db.query(DisposalCompanyMaster).filter(
            DisposalCompanyMaster.company_id == current_user.company_id,
            DisposalCompanyMaster.name.in_(active_contractors)
        ).all()
        
        if disposal_masters:
            # 別紙（搬入先一覧）のHTML生成
            appendix_html = env.get_template("template_appendix_disposal.html").render(disposal_companies=disposal_masters)
            html_content += '<div style="page-break-before: always;"></div>' + appendix_html
            
            # 許可証画像のHTML生成
            permit_images = []
            for m in disposal_masters:
                if m.permit_image_url:
                    # 相対URLを絶対ファイルパスまたはfile:// URLに変換
                    # m.permit_image_url example: "/uploads/permits/xxx.jpg"
                    local_path = os.path.join(os.getcwd(), m.permit_image_url.lstrip("/"))
                    permit_images.append({
                        "title": f"【許可証】{m.name}",
                        "url": f"file://{local_path}"
                    })
            if permit_images:
                images_html = env.get_template("template_appendix_images.html").render(images=permit_images)
                html_content += images_html

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
