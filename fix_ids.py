import re

with open('pipeline.html', 'r', encoding='utf-8') as f:
    content = f.read()

fields = [
    'pipeline_stage',
    'job_type',
    'processing_category',
    'yamabun_work_type_select',
    'job_name',
    'customer_select',
    'original_customer_id',
    'customer_name',
    'address',
    'fd_contact_name',
    'fd_email',
    'fd_phone',
    'fd_mobile',
    'fd_yamabun_management_number',
    'fd_collection_frequency',
    'fd_collection_days',
    'fd_payment_method',
    'fd_invoice_delivery',
    'fd_invoice_send_to',
    'work_date',
    'work_time',
    'price_total',
    'workers',
    'total_volume_m3',
    'notes',
    'status'
]

def replace_in_block(block, fields):
    for f_name in fields:
        block = re.sub(rf'id="{f_name}"', f'id="{f_name}_edit"', block)
        block = re.sub(rf"getElementById\('{f_name}'\)", f"getElementById('{f_name}_edit')", block)
    return block

# Find openJobDetail
open_job_start = content.find('async function openJobDetail(jobId) {')
open_job_end = content.find('async function updateJobDrawer(jobId) {')

# Find updateJobDrawer
update_job_start = content.find('async function updateJobDrawer(jobId) {')
update_job_end = content.find('async function updateDrawerDate(jobId, value) {')

if open_job_start == -1 or update_job_start == -1 or open_job_end == -1 or update_job_end == -1:
    print("Could not find functions")
    exit(1)

new_content = (
    content[:open_job_start] +
    replace_in_block(content[open_job_start:open_job_end], fields) +
    replace_in_block(content[update_job_start:update_job_end], fields) +
    content[update_job_end:]
)

with open('pipeline.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Done")
