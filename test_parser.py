from services.parser import parse_resume

data = parse_resume(
    "uploads/resumes/Adarsh_CV.pdf"
)

print(data)