import os
import re

import docx2txt
from bs4 import BeautifulSoup
from icecream import ic
from pypdf import PdfReader
from starlette.datastructures import UploadFile  # err if "from fastapi"
from streamlit.runtime.uploaded_file_manager import UploadedFile
from langchain_core.documents import Document

allowed_extensions = [
    "",
    ".txt",
    ".md",
    ".rtf",
    ".log",
    ".pdf",
    ".docx",
    ".html",
    ".htm",
]


def get_page_texts_from_pdf(file):
    reader = PdfReader(file)
    return [page.extract_text() for page in reader.pages]


DEFAULT_PAGE_START = "PAGE {page_num}:\n"
DEFAULT_PAGE_SEP = "\n" + "-" * 3 + "\n\n"


def get_text_from_pdf(file, page_start=DEFAULT_PAGE_START, page_sep=DEFAULT_PAGE_SEP):
    return page_sep.join(
        [
            page_start.replace("{page_num}", str(i)) + x
            for i, x in enumerate(get_page_texts_from_pdf(file), start=1)
        ]
    )


def extract_text(files, allow_all_ext):
    docs = []
    failed_files = []
    unsupported_ext_files = []
    for file in files:
        if isinstance(file, UploadFile):
            file_name = file.filename or "unnamed-file"  # need?
            file = file.file
        else:
            file_name = file.name
        try:
            extension = os.path.splitext(file_name)[1]
            if not allow_all_ext and extension not in allowed_extensions:
                unsupported_ext_files.append(file_name)
                continue
            if extension == ".pdf":
                for i, text in enumerate(get_page_texts_from_pdf(file)):
                    metadata = {"source": f"{file_name} (page {i + 1})"}
                    docs.append(Document(page_content=text, metadata=metadata))
            else:
                if extension == ".docx":
                    text = docx2txt.process(file)
                elif extension in [".html", ".htm"]:
                    soup = BeautifulSoup(file, "html.parser")
                    # Remove script and style elements
                    for script_or_style in soup(["script", "style"]):
                        script_or_style.extract()
                    text = soup.get_text()
                    # Replace multiple newlines with single newlines
                    text = re.sub(r"\n{2,}", "\n\n", text)
                    print(text)
                else:
                    # Treat as text file
                    if isinstance(file, UploadedFile):
                        text = file.getvalue().decode("utf-8")
                        # NOTE: not sure what the advantage is for Streamlit's UploadedFile
                    else:
                        text = file.read().decode("utf-8")
                docs.append(Document(page_content=text, metadata={"source": file_name}))
        except Exception as e:
            ic(e)
            failed_files.append(file_name)

    ic(len(docs), failed_files, unsupported_ext_files)
    return docs, failed_files, unsupported_ext_files

def format_ingest_failure(failed_files, unsupported_ext_files):
    res = (
        "Apologies, the following files failed to process:\n```\n"
        + "\n".join(unsupported_ext_files + failed_files)
        + "\n```"
    )
    if unsupported_ext_files:
        unsupported_extentions = sorted(
            list(set(os.path.splitext(x)[1] for x in unsupported_ext_files))
        )
        res += "\n\nUnsupported file extensions: " + ", ".join(
            f"`{x.lstrip('.') or '<no extension>'}`" for x in unsupported_extentions
        )
    return res