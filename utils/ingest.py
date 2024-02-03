from pypdf import PdfReader


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
