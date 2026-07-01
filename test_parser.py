from services.parser import parse_resume

data = parse_resume(
    "uploads/resumes/Aditya_Nair.docx"
)

print(data)