FROM python:3.11-bookworm

# Needed for ingesting Confluence attachments 
# # Install system packages: tesseract and poppler
# RUN apt update && apt install -y \
#     tesseract-ocr \
#     poppler-utils \
#     && apt-get clean \
#     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]


