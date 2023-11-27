import asyncio
import aiohttp

from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from langchain.schema import Document
from langchain.document_loaders import AsyncHtmlLoader, AsyncChromiumLoader
from langchain.document_loaders.async_html import default_header_template
from langchain.document_transformers import BeautifulSoupTransformer

from utils.lang_utils import get_num_tokens, limit_tokens_in_text
from utils.strings import remove_consecutive_blank_lines


async def afetch_url_aiohttp(session: aiohttp.ClientSession, url: str):
    """
    Asynchronously fetch the content from a URL.
    """
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.text()
    except aiohttp.ClientError as e:
        return f"Error: {e}"


async def afetch_urls_in_parallel_aiohttp(urls):
    """
    Asynchronously fetch multiple URLs in parallel. Return the HTML content of each URL.
    If there is an error in a particular URL, return the error message instead.
    """
    async with aiohttp.ClientSession() as session:
        tasks = [afetch_url_aiohttp(session, url) for url in urls]
        html_contents = await asyncio.gather(*tasks)

    return html_contents


MAX_PLAYWRIGHT_INSTANCES = 1


async def afetch_urls_in_parallel_chromium(urls):
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


def get_text_from_html(html_content: str, use_lc=True):
    """
    Extract text from HTML content, ignoring scripts and styles.
    """
    if use_lc:
        # Use langchain to extract text
        bs_transformer = BeautifulSoupTransformer()
        tmp_docs = [Document(page_content=html_content)]
        docs_transformed = bs_transformer.transform_documents(
            tmp_docs,
            unwanted_tags=["script", "style"],
            remove_lines=True,
            tags_to_extract=["p", "li", "div", "a"],
        )
        return docs_transformed[0].page_content
    else:
        soup = BeautifulSoup(html_content, "html.parser")
        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()
        return soup.get_text()


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


MIN_CHARS_PER_URL_CONTENT = 100


def remove_failed_fetches(texts: list[str], urls: list[str]):
    """
    Remove failed fetches from a list of text strings obtained from a list of URLs.
    """
    new_texts = []
    new_urls = []
    for text, url in zip(texts, urls):
        if text.startswith("Error: "):
            print("Error fetching URL:", text[7:])
            continue
        if len(text) < MIN_CHARS_PER_URL_CONTENT:
            print(
                f"WARNING: URL {url} has only {len(text)} characters, "
                f"less than the minimum of {MIN_CHARS_PER_URL_CONTENT}"
            )
            continue
        new_texts.append(text)
        new_urls.append(url)
    return new_texts, new_urls


def process_and_limit_texts(texts: list[str], max_tot_tokens=8000):
    texts = [clean_text(text) for text in texts]
    token_counts = [get_num_tokens(text) for text in texts]
    allowance_redistributed = [False] * len(texts)
    allowance = max_tot_tokens // (len(texts) or 1)
    while True:
        # Calculate "unused allowance" we can "give" to other texts
        unused_allowance = 0
        num_texts_with_excess = 0
        for i, (num_tokens, is_already_redistributed) in enumerate(
            zip(token_counts, allowance_redistributed)
        ):
            if is_already_redistributed:
                continue
            if num_tokens > allowance:
                num_texts_with_excess += 1
            else:
                unused_allowance += allowance - num_tokens
                allowance_redistributed[i] = True  # or will be, once we inc allowance

        # If no allowance to give, we're done
        if (
            num_texts_with_excess == 0
            or (allowance_increment := unused_allowance // num_texts_with_excess) == 0
        ):
            break

        # Distribute unused allowance and recalculate
        # print("num_texts_with_excess:", num_texts_with_excess)
        # print("allowance", allowance, end=" -> ")
        allowance += allowance_increment
        print(allowance)

    new_texts = []
    # print("process_and_limit_text: allowance:", allowance)
    for text, token_count in zip(texts, token_counts):
        # print("process_and_limit_text: text:", text[:100])
        # print("process_and_limit_text: token_count:", token_count)
        if token_count > allowance:
            # Limit tokens in text
            text, num_tokens = limit_tokens_in_text(text, max_tokens=allowance)
        # print("process_and_limit_text: token count after limiting:", num_tokens)
        new_texts.append(text)
    return new_texts


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
