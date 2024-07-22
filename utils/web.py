import asyncio
import io
import os
from enum import Enum

import aiohttp
import trafilatura
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from langchain_community.document_loaders import AsyncChromiumLoader, AsyncHtmlLoader
from langchain_community.document_transformers import BeautifulSoupTransformer
from langchain_community.document_loaders.async_html import default_header_template
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from pydantic import BaseModel

from utils.async_utils import make_sync
from utils.helpers import print_no_newline
from utils.ingest import get_text_from_pdf
from utils.output import format_exception
from utils.strings import remove_consecutive_blank_lines
from langchain_core.documents import Document

MAX_PLAYWRIGHT_INSTANCES = 5
# TODO: 1 causes afetch_urls_in_parallel_playwright to hang (semaphore?)

PLAYWRIGHT_TIMEOUT_MS = 10000
AIOHTTP_TIMEOUT_MS = 10000
PDF_TEXT_PREFIX = "PLAIN_TEXT[PDF]: "


async def afetch_url_aiohttp(
    session: aiohttp.ClientSession, url: str, retries=3, backoff_factor=0.5
):
    """
    Asynchronously fetch a URL using an aiohttp session with retry and exponential backoff.
    It extracts text from PDFs and returns HTML content otherwise.
    """
    header_template = default_header_template
    header_template["User-Agent"] = UserAgent().random

    for attempt in range(retries):
        try:
            async with session.get(url, headers=header_template) as response:
                response.raise_for_status()  # Raises exception for 4xx/5xx errors

                content_type = response.headers.get("Content-Type", "")
                if "application/pdf" in content_type:
                    # Handle PDF content
                    pdf_content = await response.read()
                    with io.BytesIO(pdf_content) as pdf_file:
                        return PDF_TEXT_PREFIX + get_text_from_pdf(pdf_file)
                else:
                    return await response.text()

        except Exception as e:
            # TODO: ClientError, asyncio.TimeoutError, etc.
            if attempt == retries - 1:
                return f"Error: {format_exception(e)}"
            # Wait for a bit before retrying
            sleep_time = backoff_factor * (2**attempt)  # Exponential backoff
            await asyncio.sleep(sleep_time)


async def afetch_urls_in_parallel_aiohttp(urls):
    """
    Asynchronously fetch multiple URLs in parallel using aiohttp.
    Return the HTML content of each URL. If there is an error in a particular URL,
    return the error message instead of that URL's content, starting with "Error: ".
    """
    timeout = aiohttp.ClientTimeout(total=AIOHTTP_TIMEOUT_MS / 1000)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [afetch_url_aiohttp(session, url) for url in urls]
        htmls = await asyncio.gather(*tasks)

    return htmls


async def afetch_url_playwright(
    url: str,
    headless=True,
    timeout=PLAYWRIGHT_TIMEOUT_MS,
    sleep_after_load_ms=0,
    **fetch_options,
):
    """
    Asynchronously fetch the content from a URL using an instance of
    Chromium (with playwright).

    If there is an error, return the error message instead.
    """
    fetch_options["timeout"] = timeout
    try:
        async with async_playwright() as pwt:
            # NOTE: consider whether to use one pwt for all parallel fetches
            # browser = await pwt.webkit.launch(headless=False)
            browser = await pwt.chromium.launch(headless=headless)
            iphone_13 = pwt.devices["iPhone 13"]
            context = await browser.new_context(**iphone_13)
            page = await context.new_page()
            try:
                await page.goto(url, **fetch_options)  # eg wait_until="networkidle"
                if sleep_after_load_ms:
                    await asyncio.sleep(sleep_after_load_ms / 1000)
                html_content = await page.content()
            except PlaywrightTimeoutError:
                # Still try to get the content
                html_content = await page.content()
                if not html_content or html_content.startswith(
                    "<html><head></head><body></body></html>"
                ):
                    html_content = "Error: timed out before any content was loaded"
            finally:
                await browser.close()
    except Exception as e:
        html_content = f"Error: {e}"
    return html_content


async def afetch_urls_in_parallel_playwright(
    urls,
    headless=True,
    timeout=PLAYWRIGHT_TIMEOUT_MS,
    sleep_after_load_ms=0,
    callback=None,
    **fetch_options,
):
    """
    Asynchronously fetch multiple URLs in parallel using
    Chromium (with playwright). Return the HTML content of each URL.
    If there is an error in a particular URL, return the error message instead.

    Uses a semaphore to limit the number of concurrent playwright instances to
    MAX_PLAYWRIGHT_INSTANCES.
    """
    semaphore = asyncio.Semaphore(MAX_PLAYWRIGHT_INSTANCES)

    async def fetch_with_semaphore(url):
        async with semaphore:
            res = await afetch_url_playwright(
                url,
                headless=headless,
                timeout=timeout,
                sleep_after_load_ms=sleep_after_load_ms,
                **fetch_options,
            )
            if callback:
                callback(url, res)
            return res

    tasks = [fetch_with_semaphore(url) for url in urls]
    htmls = await asyncio.gather(*tasks)
    return htmls


def fetch_urls_playwright(urls):
    pass


#     transport = await self._make_subprocess_transport(
#                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#   File "C:\Users\micro\AppData\Local\Programs\Python\Python311\Lib\asyncio\base_events.py",
#   line 502, in _make_subprocess_transport
#     raise NotImplementedError


async def afetch_urls_in_parallel_chromium_loader(urls):
    """
    Asynchronously fetch multiple URLs in parallel using a headless instance of
    Chromium (with playwright). Return the HTML content of each URL.
    If there is an error in a particular URL, return the error message instead.

    Uses a semaphore to limit the number of concurrent playwright instances to
    MAX_PLAYWRIGHT_INSTANCES.
    """
    semaphore = asyncio.Semaphore(MAX_PLAYWRIGHT_INSTANCES)
    loader = AsyncChromiumLoader([])

    async def fetch_with_semaphore(url):
        async with semaphore:
            return await loader.ascrape_playwright(url)

    tasks = [fetch_with_semaphore(url) for url in urls]
    htmls = await asyncio.gather(*tasks)
    return htmls


async def afetch_urls_in_parallel_html_loader(urls):
    """
    Asynchronously fetch multiple URLs in parallel using AsyncHtmlLoader.
    Return the HTML content of each URL.
    """

    header_template = default_header_template
    header_template["User-Agent"] = UserAgent().random
    loader = AsyncHtmlLoader(urls, header_template=header_template)
    htmls = await loader.fetch_all(urls)
    return htmls


def fetch_urls_with_lc_html_loader(urls):
    """
    Fetch multiple URLs using AsyncHtmlLoader. Return the HTML content of each URL.

    NOTE: The current implementation of AsyncHtmlLoader's load() appears to first fetch the URLs
    in parallel, but then to fetch them again sequentially.
    """
    header_template = default_header_template
    header_template["User-Agent"] = UserAgent().random
    loader = AsyncHtmlLoader(urls, header_template=header_template)
    docs = loader.load()
    htmls = [doc.page_content for doc in docs]
    return htmls


def clean_text(text: str, break_multi_headlines=False):
    """
    Perform some basic cleaning on text extracted from HTML, such as removing
    consecutive blank lines and other unwanted whitespace.
    """
    # Break into lines and remove leading/trailing whitespace
    lines = (line.strip() for line in text.splitlines())

    if break_multi_headlines:
        # Break multi-headlines (2+ spaces) into a line each
        lines = (phrase.strip() for line in lines for phrase in line.split("  "))

    lines = remove_consecutive_blank_lines(lines)
    text = "\n".join(lines)
    return text


class TextFromHtmlMode(Enum):
    BASIC = "BASIC"
    LC_BS_TRANSFORMER = "LC_BS_TRANSFORMER"
    TRAFILATURA = "TRAFILATURA"


def get_text_from_html(
    html_content: str,
    mode=TextFromHtmlMode.TRAFILATURA,
    clean=True,
    break_multi_headlines=False,
) -> str:
    """
    Extract text from an HTML string.
    """
    if html_content.startswith("Error: "):
        return html_content

    if mode == TextFromHtmlMode.TRAFILATURA:
        # https://trafilatura.readthedocs.io/en/latest/usage-python.html
        text = trafilatura.extract(
            html_content,
            include_links=True,
            favor_recall=True,
            config=None,
            settingsfile="./config/trafilatura.cfg",
            output_format="txt",
        )
        # NOTE: can try extracting with different settings till get the length we want
        clean = False  # trafilatura already does some cleaning
    elif mode == TextFromHtmlMode.LC_BS_TRANSFORMER:
        # Use langchain to extract text
        bs_transformer = BeautifulSoupTransformer()
        tmp_docs = [Document(page_content=html_content)]
        docs_transformed = bs_transformer.transform_documents(
            tmp_docs,
            unwanted_tags=["script", "style"],
            remove_lines=True,
            tags_to_extract=["p", "li", "div", "a"],
        )
        text = docs_transformed[0].page_content
    else:
        soup = BeautifulSoup(html_content, "html.parser")
        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()
        text = soup.get_text()

    if not text:  # it could be None
        text = ""
    elif clean:
        text = clean_text(text, break_multi_headlines=break_multi_headlines)
    return text


MIN_WORDS_PER_URL_CONTENT = 80


def is_html_text_ok(text: str) -> bool:
    """
    Return True if the text extracted from an HTML string appears to be from a
    successfully fetched website.

    Specifically, return True if it has at least MIN_WORDS_PER_URL_CONTENT words.
    """
    return len(text.split()) >= MIN_WORDS_PER_URL_CONTENT


def remove_failed_fetches(
    texts: list[str], urls: list[str]
) -> tuple[list[str], list[str]]:
    """
    Remove failed fetches from a list of text strings obtained from a list of URLs.

    Return the filtered lists of texts and URLs.
    """
    new_texts = []
    new_urls = []
    for text, url in zip(texts, urls):
        if text.startswith("Error: "):
            print(f"Error fetching URL {url}:\n{text[7:]}")
            continue
        if not is_html_text_ok(text):
            print(
                f"Skipping URL {url}: retrieved text has only {len(text)} characters, "
                f"less than the minimum of {MIN_WORDS_PER_URL_CONTENT}"
            )
            continue
        new_texts.append(text)
        new_urls.append(url)
    return new_texts, new_urls


class LinkData(BaseModel):
    text: str | None = None
    error: str | None = None
    num_tokens: int | None = None
    is_ingested: bool = False

    @classmethod
    def from_raw_content(cls, content: str):
        """
        Return a LinkData instance from the HTML or plain text content of a URL.
        """
        if content.startswith("Error: "):
            return cls(error=content)
        if content.startswith(PDF_TEXT_PREFIX):
            return cls(text=content[len(PDF_TEXT_PREFIX) :])
        text = get_text_from_html(content)
        if is_html_text_ok(text):
            return cls(text=text)
        return cls(text=text, error="UNACCEPTABLE_EXTRACTED_TEXT")


def get_batch_url_fetcher():
    """Decide which fetcher to use for the links."""
    if not os.getenv("USE_PLAYWRIGHT"):
        return make_sync(afetch_urls_in_parallel_aiohttp)

    def link_fetcher(links):
        return make_sync(afetch_urls_in_parallel_playwright)(
            links, callback=lambda url, html: print_no_newline(".")
        )

    return link_fetcher


# NOTE: Fetching without chromium often leads to empty content (with chromium, that can still happen; also, it's slow). For example, of the following 27 URLs, only 8 have non-empty content:

#  links = [
#         "https://www.cnn.com/middleeast/live-news/israel-hamas-was-gaza-news-11-23-23/index.html",
#         "https://www.nbcnews.com/news/world/live-blog/israel-hamas-war-live-updates-rcna126373",
#         "https://www.cnbc.com/2023/11/23/israel-hamas-war-live-updates-news-on-gaza-conflict.html",
#         "https://www.aljazeera.com/where/israel/",
#         "https://www.aljazeera.com/news/liveblog/2023/11/23/israel-hamas-war-live-israel-pounds-gaza-ahead-of-expected-truce",
#         "https://www.aljazeera.com/news/liveblog/2023/11/22/israel-hamas-war-live-israeli-government-to-vote-on-gaza-truce-deal",
#         "https://www.cnn.com/middleeast/live-news/israel-hamas-was-gaza-news-11-23-23/index.html",
#         "https://www.nbcnews.com/news/world/live-blog/israel-hamas-war-live-updates-rcna126373",
#         "https://www.cnbc.com/2023/11/23/israel-hamas-war-live-updates-news-on-gaza-conflict.html",
#         "https://www.cnbc.com/2023/11/23/ukraine-war-live-updates-latest-news-on-russia-and-the-war-in-ukraine.html",
#         "https://www.aljazeera.com/news/2023/11/23/putin-uses-gaza-to-defend-his-war-while-bombing-civilians-in-ukraine",
#         "https://www.theguardian.com/world/ukraine",
#         "https://www.bbc.com/news/topics/c302m85q5ljt?page=2",
#         "https://www.bbc.com/news/live/world-middle-east-67481139",
#         "https://youtube.com/watch?v=QiyC3NzwI7s",
#         "https://www.cnn.com/middleeast/live-news/israel-hamas-was-gaza-news-11-23-23/index.html",
#         "https://www.nbcnews.com/news/world/live-blog/israel-hamas-war-live-updates-rcna126373",
#         "https://www.aljazeera.com/news/liveblog/2023/11/23/israel-hamas-war-live-israel-pounds-gaza-ahead-of-expected-truce",
#         "https://www.nbcnews.com/news/world/live-blog/israel-hamas-war-live-updates-rcna126373",
#         "https://www.cnbc.com/2023/11/23/israel-hamas-war-live-updates-news-on-gaza-conflict.html",
#         "https://www.aljazeera.com/news/liveblog/2023/11/23/israel-hamas-war-live-israel-pounds-gaza-ahead-of-expected-truce",
#         "https://www.aljazeera.com/news/2023/11/23/mixed-reactions-among-palestinians-israelis-over-prisoner-captive-exchange",
#         "https://apnews.com/hub/israel-hamas-war",
#         "https://apnews.com/article/israel-hamas-war-ceasefire-what-to-know-af1cfbc9dcaa1485ed7a9efaca7ec2b7",
#         "https://www.aljazeera.com/where/syria/",
#         "https://apnews.com/hub/syria",
#         "https://www.cnn.com/world/middleeast/syria",
#     ]
