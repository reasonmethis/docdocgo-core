
# DocDocGo

## Table of Contents

- [Introduction](#introduction)
- [Installation](#installation)
- [Ingesting Documents](#ingesting-documents)
- [Running the Bot](#running-the-bot)
- [Running the Containerized Application](#running-the-containerized-application)
- [Advanced Usage](#advanced-usage)

## Introduction

DocDocGo is a chatbot that can ingest documents you provide and use them in its responses. In other words, it is like ChatGPT that "knows" information from your documents. It comes in two versions: DocDocGo Carbon (commercial, sold to Carbon Inc.) and DocDocGo Core (this repository).

There are several well-developed commercial applications allowing you to chat with your data (e.g. [Inkeep](https://inkeep.com/), [Mendable](https://www.mendable.ai/)). DocDocGo is a much smaller project, however, as of the time of writing, some of its features below appear to be unique to it.

Features:

- it provides [several response modes](#advanced-usage) ("chat", "detailed report", "quotes", "web research")
- it allows to [query](#advanced-usage) simultaneously based on semantics and on substrings in documents
- it uses an algorithm to _dynamically distribute its "memory"_ between the source documents and the current conversation based on the relevance of the documents to the conversation
- it provides links to source documents
- it has been tuned to be resilient to "jail-breaking" it (by contrast, some other applications allow you to access their "internals")

For reference, the commercial version of DocDocGo (not available here) has these features:

- it is integrated with a Google Chat App
- it interacts with the client company's Confluence documentation
- it offers the ability to provide feedback on the quality of its responses
- it has a database for conversations and feedback and allowed to resume the conversation

## Installation

### 1. Clone this repository and cd into it

```bash
git clone https://github.com/reasonmethis/docdocgo-core.git
cd docdocgo-core
```

### 2. Create and activate a virtual environment

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

If you want to try using the newest versions of the packages, you can instead run:

```bash
pip install langchain openai chromadb tiktoken unstructured flask waitress beautifulsoup4
```

It's possible you may get the error message:

```bash
Microsoft Visual C++ 14.0 or greater is required. Get it with "Microsoft C++ Build Tools": https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

If this happens you will need to install the Microsoft C++ Build Tools. You can get them [here](https://visualstudio.microsoft.com/visual-cpp-build-tools/). Then try installing the requirements again.

### 4. Copy the `.env.example` file to `.env` and fill in the values

```bash
cp .env.example .env
```

At first, you can simply fill in your [OpenAI API key](https://platform.openai.com/signup) and leave the other values as they are.

## Ingesting Documents

> You can skip this section if you just want to quickly try out the bot - the repo comes with a default database, obtained by ingesting this very README.

To ingest your documents and use them when chatting with the bot, follow the steps below.

### 1. Set the input and output directories

Set the following values in the `.env` file:

```bash
DOCS_TO_INGEST_DIR_OR_FILE="./docs-private/my-awesome-data"
SAVE_VECTORDB_DIR="./dbs-private/my-awesome-data" 

VECTORDB_DIR="./dbs-private/my-awesome-data" 
```

Feel free to use your own directory names. The `VECTORDB_DIR` value is not used for ingestion, it's the directory where the bot will look for the database when it's started.

### 2. Run the ingestion script

To ingest the documents, run:

```bash
python ingest_local_docs.py
```

The script will show you the ingestion settings and ask for confirmation before proceeding.

## Running the Bot

To chat with the bot locally, run:

```bash
python docdocgo.py
```

Alternatively, DocDocGo also comes with a flask server, which can be run with:

```bash
waitress-serve --listen=0.0.0.0:8000 main:app
```

We won't cover the details of using the flask server in this README, but the necessary format for requests can be relatively easily gleaned from `main.py`. The server was used in the commercial version of DocDocGo to interact with the accompanying Google Chat App. It can be similarly used to integrate DocDocGo into any other chat application, such as a Telegram or Slack bot.

## Running the Containerized Application

DocDocGo is also containerized with Docker. The following steps can be used to run the containerized application.

### 1. Build the Docker image

```bash
docker build -t docdocgo:latest .
```

### 2. Run the Docker container

Run the Docker container and expose port 8000:

```bash
docker run --name docdocgo -p 8000:8000 -d -i -t docdocgo:latest /bin/bash
```

### 3. Open a terminal inside the container

```bash
docker exec -it docdocgo /bin/bash
```

### 4. Start the application

Start the flask server inside the Docker container:

```bash
waitress-serve --listen=0.0.0.0:8000 main:app
```

If you need to restart and rebuild an existing Docker container (e.g. if there are changes to the code or database):

```bash
docker stop docdocgo
docker rm docdocgo
```

or simply:

```bash
docker rm -f docdocgo
```

After that, follow the above steps to rebuild the container and restart the service.

## Advanced Usage

### Response Modes

DocDocGo has several response modes:

- Chat Mode - mode for a regular conversation about ingested documents or any other topic.
- Detailed Report Mode - generate a detailed report that summarizes all of the information retrieved in response to the query.
- Quotes Mode - generate a list of quotes from the documents retrieved in response to the query.
- Web Research Mode - perform web research about your query and generate a report

To select a mode, start your message with the corresponding slash command: `/chat`, `/details`, `/quotes`, `/web`. For example:

```markdown
/details When is the conference?
```

If you don't specify a mode, DocDocGo will use the default mode, which is set by the `DEFAULT_MODE` variable in the `.env` file (initially set to `\chat`).

### Querying based on substrings

DocDocGo allows you to query your documents simultaneously based on the meaning of your query and on keywords (or any substrings) in the documents. To do this, simply include the substrings in your query, enclosed in quotes. For example, if your message is:

```markdown
When is "Christopher" scheduled to attend the conference?
```

DocDocGo will only consider document chunks that contain the substring "Christopher" when answering your query.
