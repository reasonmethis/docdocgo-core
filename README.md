# DocDocGo

## Table of Contents

- [Introduction](#introduction)
- [(Very) Quickstart](#very-quickstart)
- [Features](#features)
- [Installation](#installation)
- [Running DocDocGo](#running-docdocgo)
- [Ingesting Documents](#ingesting-documents)
- [Response Modes](#response-modes)
- [Querying based on substrings](#querying-based-on-substrings)
- [Contributing](#contributing)
- [Appendix](#appendix)
  - [Minified Requirements](#minified-requirements)
  - [Running the Containerized Application](#running-the-containerized-application)
  - [License](#license)

## Introduction

DocDocGo is a chatbot that can ingest documents you provide and use them in its responses. In other words, it is like ChatGPT that "knows" information from your documents. Instead of using your documents, it can also find and ingest information from the Internet and generate iteratively improving reports on any topic you want to research. It comes in two versions: DocDocGo Carbon (commercial, sold to Carbon Inc.) and DocDocGo Core (this repository).

## (Very) Quickstart

You will see more detailed setup instructions below, but here they are in a nutshell:

1. Install requirements with `pip install -r requirements.txt`
2. Create `.env` using `.env.example`
3. Run `streamlit run streamlit_app.py`

That's it, happy chatting!

## Features

- Comes with a Streamlit UI, but can also be run in console mode or as a flask app
- Provides [multiple response modes](#response-modes) ("chat", "detailed report", "quotes", "quick web research", "infinite web research", "URL or local docs ingestion", "URL summarization")
- Allows to [query](#querying-based-on-substrings) simultaneously based on semantics and on substrings in documents
- Allows to create and switch between multiple document collections
- Automatically ingests content retrieved during web research into a new document collection
- Provides links to source documents or websites
- Dynamically manages its "memory" allocations for the source documents vs the current conversation, based on the relevance of the documents to the conversation

For reference, DocDocGo Carbon (not available here) has these features:

- It is integrated with a Google Chat App
- Interacts with the client company's Confluence documentation
- Offers the ability to provide feedback on the quality of its responses
- Has a database for conversations and feedback and allows to resume the conversation

## Installation

### 1. Clone this repository and cd into it

```bash
git clone https://github.com/reasonmethis/docdocgo-core.git
cd docdocgo-core
```

### 2. Create and activate a virtual environment

First, make sure you are using Python 3.11 or higher. If you prefer using the exact version that the code was developed with, please use Python 3.11.6. Then, create a virtual environment and activate it.

On Windows:

```bash
python -m venv .venv && .venv\scripts\activate
```

On Mac/Linux:

```bash
python -m venv .venv && source .venv/bin/activate
```

### 3. Install the requirements

Run:

```bash
pip install -r requirements.txt
```

> Note: if you would like to see a "minified" version of the requirements, please see the [Appendix](DOCS-APPENDIX.md#minified-requirements).

It's possible you may get the error message:

```bash
Microsoft Visual C++ 14.0 or greater is required. Get it with "Microsoft C++ Build Tools": https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

If this happens you will need to install the Microsoft C++ Build Tools. You can get them [here](https://visualstudio.microsoft.com/visual-cpp-build-tools/). Then try installing the requirements again.

### 4. Copy the `.env.example` file to `.env` and fill in the values

```bash
cp .env.example .env
```

At first, you can simply fill in your [OpenAI API key](https://platform.openai.com/signup) and leave the other values as they are. Please see `.env.example` for additional details.

## Running DocDocGo

The easiest way to interact with the bot is to run its Streamlit UI:

```bash
streamlit run streamlit_app.py
```

If you prefer to chat with the bot in the console, you can instead run:

```bash
python docdocgo.py
```

Finally, DocDocGo also comes with a flask server, which can be run with:

```bash
waitress-serve --listen=0.0.0.0:8000 main:app
```

We won't cover the details of using the flask server in this README, but the necessary format for requests can be relatively easily gleaned from `main.py`. The server was used in the commercial version of DocDocGo to interact with the accompanying Google Chat App. It can be similarly used to integrate DocDocGo into any other chat application, such as a Telegram or Slack bot.

## Ingesting Documents

> You can skip this section and still be able to use all of the bot's features. The repo comes with a database preconfigured with a default document collection, obtained by ingesting this very README and other documentation. Additionally, using the `/research` command (see [Response Modes](#response-modes)) automatically ingests the results of the web research into a new document collection.

To ingest your documents and use them when chatting with the bot, you can simply type `/ingest` if you are using the Streamlit UI. In the console mode, follow the instructions below.

### 1. Fill in the desired ingestion settings in the `.env` file

Set the following values in the `.env` file:

```bash
DOCS_TO_INGEST_DIR_OR_FILE="path/to/my-awesome-data"
COLLECTON_NAME_FOR_INGESTED_DOCS5="my-awesome-collection"
```

### 2. Run the ingestion script

To ingest the documents, run:

```bash
python ingest_local_docs.py
```

The script will show you the ingestion settings and ask for confirmation before proceeding.

## Response Modes

DocDocGo has several response modes that activate its various capabilites:

- Chat with Docs - the default mode, used for chatting about your ingested documents or any other topic.
- Regular Chat - chat with DocDocGo without using your ingested documents.
- Detailed Report - a detailed report on all of the content from your documents retrieved in response to your query.
- Quotes - generate a list of quotes from the documents retrieved in response to the query.
- "Infinite" Web Research - perform in-depth Internet research about your query, ingest retrieved content, and generate report(s) (see [below](#infinite-web-research-mode) for details).
- Basic Web Research - perform quick web research about your query and generate a report without ingesting the retrieved content.
- Ingest - ingest the content of a URL or your local documents
- Summarize - summarize the content of a URL and ingest it for follow-up queries
- Database Management - manage your document collections: switch between them, rename, delete, etc.
- Help - see the help message.

To select a mode, start your message with the corresponding prefix: `/docs`, `/chat`, `/details`, `/quotes`, `/research`, `/web`, `/ingest`, `/summarize`, `/db`, or `/help`. You can also use just the first two letters of a prefix. For example:

```markdown
/re What are the ELO ratings of the top chess engines?
```

or

```markdown
/summarize https://blog.rwkv.com/p/eagle-7b-soaring-past-transformers
```

If you don't specify a mode, DocDocGo will use the default mode, which is set by the `DEFAULT_MODE` variable in the `.env` file (defaulting to `/docs`). For the Database Management Mode, start by sending the `/db` command without any arguments. DocDocGo will then show you the available options.

### "Infinite" Web Research Mode

This is a powerful feature of DocDocGo that allows you to perform iterative web research about your query, ingest retrieved content, and generate a report, which the bot will try to improve iteratively by using more and more sources, for as many steps as you specify. Use this mode in three steps:

**Step 1.** Start the research by sending a message starting with `/research` and followed by your query. For example:

```markdown
/research What are the best ways to improve my memory? Just bullet points, please.
```

> You can also enter `/research` without a query. You will then get a "cheatsheet" showing you all the ways to use the `/research` command, which extend far beyond the `deeper` option explained below.

**Step 2.** After DocDocGo has finished the first iteration of the research, it will compose its initial report. If you want to continue the research, simply type `/research` to see your options. The main option is `/research deeper N`, where `N` is the number of times you want to double the number of sources that go into the report. Using this command will kick off a series of research steps, where each step involves either (a) fetching more sources and composing an alternative report or (b) combining information from two existing reports into a new, higher-level report.

This is the "infinite" research capability of DocDocGo. Setting `N` to 5, for example, will result in a report that is based on 32x more sources than the initial report (around 200). This will take a while, of course, and you can abort at any time by reloading the app.

> For more options, you can type `/research` without any arguments or ask DocDocGo for help.

**Step 3. Here's the awesome part:** The fetched content will be automatically ingested into a new collection. This means you can go beyond the report and ask follow-up questions, with DocDocGo using all of the web pages it fetched as its knowledge base.

You could even have it run overnight and come back to a huge knowledge base on your desired topic!

> Each research iteration is very cheap (typically ~1-2 cents if using the default gpt-3.5 model), but even tiny costs can add up if you do thousands of iterations.

## Querying based on substrings

DocDocGo allows you to query your documents simultaneously based on the meaning of your query and on keywords (or any substrings) in the documents. To do this, simply include the substrings in your query, enclosed in quotes. For example, if your message is:

```markdown
When is "Christopher" scheduled to attend the conference?
```

DocDocGo will only consider document chunks that contain the substring "Christopher" when answering your query.

## Contributing

Contributions are welcome! If you have any questions or suggestions, please open an issue or a pull request.

## Appendix

### Minified Requirements

Installing the following packages will also install all of the other requirements:

```bash
langchain==0.0.352
chromadb==0.4.21
openai==1.6.1
tiktoken==0.5.2
beautifulsoup4==4.12.2
docx2txt==0.8
pypdf==4.0.0
trafilatura==1.6.3
fake-useragent==1.4.0
python-dotenv==1.0.0
streamlit==1.29.0
playwright==1.40.0
Flask==3.0.0
google-cloud-firestore==2.14.0
```

### Running the Containerized Application

> Note: check the Dockerfile to make sure the requirements are up to date.

DocDocGo is also containerized with Docker. The following steps can be used to run the containerized flask server.

#### 1. Build the Docker image

```bash
docker build -t docdocgo:latest .
```

#### 2. Run the Docker container

Run the Docker container and expose port 8000:

```bash
docker run --name docdocgo -p 8000:8000 -d -i -t docdocgo:latest /bin/bash
```

#### 3. Open a terminal inside the container

```bash
docker exec -it docdocgo /bin/bash
```

#### 4. Start the application

Start the flask server inside the Docker container:

```bash
waitress-serve --listen=0.0.0.0:8000 main:app
```

If there are changes to the code or database, you will need to rebuild and rerun the container. Start by stopping and removing the container:

```bash
docker stop docdocgo
docker rm docdocgo
```

After that, follow the above steps to rebuild the container and restart the service.

### License

MIT License

Copyright (c) 2024 Dmitriy Vasilyuk

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
