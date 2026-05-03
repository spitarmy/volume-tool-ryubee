from email.mime.base import MIMEBase
part = MIMEBase('application', 'octet-stream')
filename = "Invoice_2026-04_京都テスト株式会社.pdf"
try:
    part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
    print("Success")
except Exception as e:
    print("Exception:", type(e), e)
