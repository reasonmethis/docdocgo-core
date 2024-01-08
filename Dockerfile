FROM python:3.11-bookworm

# Needed for ingesting Confluence attachments 
# # Install system packages: tesseract and poppler
# RUN apt update && apt install -y \
#     tesseract-ocr \
#     poppler-utils \
#     && apt-get clean \
#     && rm -rf /var/lib/apt/lists/*

# Install Python package dependencies
RUN pip install langchain chromadb openai tiktoken beautifulsoup4 trafilatura \
    fake-useragent python-dotenv streamlit playwright Flask unstructured waitress \
    beautifulsoup4 Pillow pytesseract docx2txt pdf2image xlrd reportlab svglib \
    google-cloud-firestore

# Copy all application files into the container
COPY . .

# RUN mkdir /test-docs
# RUN mkdir /test-dbs


