
# DocDocGo

## Table of Contents

- [Introduction](#introduction)
- [Installation](#installation)
- [Ingesting Documents](#ingesting-documents)
- [Running the Bot](#running-the-bot)
- [Running the Containerized Application](#running-the-containerized-application)
- [Response Modes](#response-modes)
- [Querying based on substrings](#querying-based-on-substrings)
- [Contributing](#contributing)

## Introduction

DocDocGo is a chatbot that can ingest documents you provide and use them in its responses. In other words, it is like ChatGPT that "knows" information from your documents. Instead of using your documents it can also ingest find and ingest information from the Internet and generate iteratively improving reports on any topic you want to research. It comes in two versions: DocDocGo Carbon (commercial, sold to Carbon Inc.) and DocDocGo Core (this repository).

## Features

- Provides [several response modes](#response-modes) ("chat", "detailed report", "quotes", "web research", "iterative web research")
- Allows to [query](#querying-based-on-substrings) simultaneously based on semantics and on substrings in documents
- Dynamically manages its "memory" allocations for the source documents vs the current conversation, based on the relevance of the documents to the conversation
- Allows to create and switch between multiple document collections
- Automatically ingests content retrieved during web research into a new document collection
- Provides links to source documents or websites
- Has been tuned to be resilient to "jail-breaking" (by contrast, in some well-known commercial applications it's possible to access the "internals")

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

> You can skip this section and still try out all of the bot's features. The repo comes with a database preconfigured with a default document collection, obtained by ingesting this very README. Additionally, using the `/research` command (see [Response Modes](#response-modes)) automatically ingests the results of the web research into a new document collection.

To ingest your documents and use them when chatting with the bot, follow the steps below.

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

## Running the Bot

The easiest way to interact with the bot is to run its web UI:

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

## Running the Containerized Application

DocDocGo is also containerized with Docker. The following steps can be used to run the containerized flask server.

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

If there are changes to the code or database, you will need to rebuild and rerun the container. Start by stopping and removing the container:

```bash
docker stop docdocgo
docker rm docdocgo
```

After that, follow the above steps to rebuild the container and restart the service.

## Response Modes

DocDocGo has several response modes:

- Chat with Docs Mode - the main mode, used for chatting about your ingested documents or any other topic.
- Regular Chat Mode - chat with DocDocGo without using your ingested documents.
- Detailed Report Mode - a detailed report on all of the content from your documents retrieved in response to your query.
- Quotes Mode - generate a list of quotes from the documents retrieved in response to the query.
- Iterative Web Research Mode - perform iterative web research about your query, ingest retrieved content, and generate a report (see [below](#iterative-web-research-mode) for details).
- Basic Web Research Mode - perform web research about your query and generate a report without ingesting the retrieved content.
- Database Management Mode - manage your document collections: switch between them, rename, delete, etc.

To select a mode, start your message with the corresponding slash command: `/docs`, `/chat`, `/details`, `/quotes`, `/research`, `/web`, `/db`, or `/help`. For example:

```markdown
/details When is the conference?
```

If you don't specify a mode, DocDocGo will use the default mode, which is set by the `DEFAULT_MODE` variable in the `.env` file (initially set to `/docs`). For the Database Management Mode, start by sending the `/db` command without any arguments. DocDocGo will then show you the available options.

### Iterative Web Research Mode

Iterative Web Research Mode is a powerful feature of DocDocGo that allows you to perform iterative web research about your query, ingest retrieved content, and generate a report, which the bot will try to improve with every iteration. Use this mode in three steps:

**Step 1.** Start the research by sending a message starting with `/research` and your query. For example:

```markdown
/research What are the best ways to improve my memory?
```

**Step 2.** After DocDocGo has finished the first iteration of the research, it will compose its initial report. If you want to continue the research, simply send the `/research` command without a query. DocDocGo will fetch more content from the web and use it to improve the report. You can continue this process as many times as you want.

**Step 3.** All of the content retrieved during the research will be automatically ingested into a new document collection, which will become the current collection. You can then use it in the other response modes, e.g. by asking questions about the collected content.

## Querying based on substrings

DocDocGo allows you to query your documents simultaneously based on the meaning of your query and on keywords (or any substrings) in the documents. To do this, simply include the substrings in your query, enclosed in quotes. For example, if your message is:

```markdown
When is "Christopher" scheduled to attend the conference?
```

DocDocGo will only consider document chunks that contain the substring "Christopher" when answering your query.

## Contributing

Contributions are welcome! If you have any questions or suggestions, please open an issue or a pull request.

## License

MIT License

Copyright (c) 2023 Dmitriy Vasilyuk

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
