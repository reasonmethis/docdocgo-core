# DocDocGo

## Table of Contents

- [Introduction](#introduction)
- [(Very) Quickstart](#very-quickstart)
- [Features](#features)
- [Installation](#installation)
- [Running DocDocGo](#running-docdocgo)
- [Using DocDocGo](#using-docdocgo)
- [Research Commands](#research-commands)
- [Database Management](#database-management)
- [Ingesting Documents](#ingesting-documents)
- [Querying based on substrings](#querying-based-on-substrings)
- [Contributing](#contributing)
- [Appendix](#appendix)
  - [Minified Requirements](#minified-requirements)
  - [Ingesting Documents in Console Mode](#ingesting-documents-in-console-mode)
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
- Provides [multiple response modes](#using-docdocgo) ("chat", "detailed report", "quotes", "quick web research", "infinite web research", "URL or local docs ingestion", "URL summarization")
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

## Using DocDocGo

The general pattern for queries is to enter one of the prefixes below followed by your message. Different prefixes activate different capabilities of DocDocGo. A prefix is optional, if you just enter a message the `/docs` prefix is used.

Here's what each prefix does. Most important ones:

- `/research <your query>`: perform "infinite" Internet research, ingesting websites into a collection
- `/docs <your query>`: chat about your currently selected doc collection (or a general topic)
- `/ingest`: upload your documents and ingest them into a collection
- `/ingest https://some.url.com`: retrieve a URL and ingest into a collection
- `/summarize https://some.url.com`: retrieve a URL, summarize and ingest into a collection
- `/db`: manage your doc collections (select, rename, etc.)
- `/help <your query>`: get help with using DocDocGo

Other prefixes:

- `/details <your query>`: get details about the retrieved documents
- `/quotes <your query>`: get quotes from the retrieved documents
- `/web <your query>`: perform web searches and generate a report
- `/chat <your query>`: regular chat, without retrieving docs or websites

Example queries:

- `/research What are this month's most important AI news?`
- `/research` (to see research options, including the "infinite" research)
- `/research deeper` (to expand the research to cover more sources)
- `/re deeper` (same - first two letters of a command are enough)
- `/docs Tell me just the ones related to OpenAI`
- `/chat Reformat your previous answer as a list of short bullet points`

We'll delve into the most important commands in more detail in the sections below. Another way to get help is to simply ask DocDocGo itself. Simply type `/help` followed by your question. If the default `docdocgo-documentation` collection is selected you don't even need to use the `/help` prefix.

## Research Commands

We'll first provide a "cheatsheet" of all of the research options, and then go over them individually and provide more detailed information.

>_KB_ stands for _knowledge base_, also known as a _collection_.

### Overview

Here are the most important commands you can use for Internet research:

- `/research <your query>`: start new Internet research, generate report, create KB from fetched sites
- `/research deeper`: expand report and KB to cover 2x more sites as current report
- `/research deeper 3`: perform the above 3 times (careful - time/number of steps increases exponentially)

You can also use the following commands:

- `/research new <your query>`: same as without `new` (can use if the first word looks like a command)
- `/research more`: keep original query, but fetch more websites and create new report version
- `/research combine`: combine reports to get a report that takes more sources into account
- `/research auto 42`: performs 42 iterationso of "more"/"combine"
- `/research iterate`: fetch more websites and iterate on the previous report
- `/research <cmd> 42`: repeat command such as `more`, `combine`, etc. 42 times

You can also view the reports:

- `/research view main`: view the main report (`main` can be omitted)
- `/research view stats`: view just the report stats
- `/research view base`: view the base reports
- `/research view combined`: view the combined reports

Let's go over the commands in more detail to get a better understanding of what they do and the differences between them.

### The `iterate` subcommand

If you type `/research iterate`, DocDocGo will fetch more content from the web and use it to try to improve the report. If you type `/research iterate N`, DocDocGo will automatically do `N` repetitions of the `/research iterate` command. Each repetition will fetch more content related to your original query and produce a new version of the report. All fetched content will be added to a KB (aka _collection_) for any follow-up questions.

> If you are doing multiple iterations and want to abort, simply reload the app.

### The `deeper` subcommand

The above approach sounds neat, but it doesn't always work in practice, especially if you use a not-so-smart model, like GPT-3.5. Specifically, it sometimes treats the information from the latest small batch of sources on an equal or higher footing than the information in the pre-existing report, even when the latter is based on many more sources and thus should be prioritized. Important information can then be lost and the report can become worse after a new iteration, not better.

That's why we have the `/research deeper` command. Instead of using new sources to try to directly improve the report, it uses a combination of `more` and `combine` operations to generate _separate_ reports from additional sources and then combine them with the existing report(s) in a way that doesn't unfairly prioritize the new sources. Each run of the `/research deeper` command will double the number of sources in the report.

> As always, all fetched content will be added to the collection for any follow-up chat.

### The recommended workflow for "infinite" research

The "infinite" research capability of DocDocGo comes from the ability to automatically perform multiple repetitions of the `deeper` command (and other research commands). Simply run `/research deeper N`, where `N` is a number, to automatically run the `deeper` command `N` times, each time doubling the number of sources. Setting `N` to 5, for example, will result in a report that is based on 32x more sources than the initial report (around 200). This will take a while, of course, and you can abort at any time by reloading the app.

Here's the simplest workflow for research:

1. Start with `/research <your query>` to generate a report based on the initial sources.
2. Decide on the next step:  
  a. If you are happy with the report, you can stop here.  
  b. If the report is completely off, you can go back to step 1 and try a new query.  
  c. Otherwise, continue to step 3.
3. Use `/research deeper N` to perform `N` iterations of the `deeper` command. Don't set `N` too high, since every such iteration **doubles** the number of sources in the report.
4. Ask any follow-up questions you have.

### The `more` and `combine` subcommands

What are these `more` and `combine` operations? `/research more` allows you to fetch more content from the web and generate a _separate_ report, without affecting the original report. This is useful if you want to see what else is out there, but don't want to risk messing up the original report.

Such separate reports are called _base reports_. If you'd like to combine the most important information from two base reports into one report, you can use the `/research combine` command. It will automatically find the two highest-level reports (at the same level) that haven't been combined yet and combine them. "Level" here roughly corresponds to the number of sources that went into the report. More precisely, base reports have level 0. When two reports are combined, the level of the new report is 1 higher than the level of the two reports that were combined.

### The `auto` subcommand

The `/research auto` command is a combination of the `/research more` and `/research combine` commands. It automatically selects one or the other. If there are reports to combine, it will use the `/research combine` command. Otherwise, it will use the `/research more` command to fetch more content from the web and generate a new base report.

You can request multiple iterations of this command. For example, `/research auto 42` will automatically perform 42 iterations of `/research auto`. (To abort, simply reload the app.)

You can add a number to the end of the `/research more` and `/research combine` commands as well to repeat them multiple times.

### The relationship between the `auto` and `deeper` commands

Both of these commands can be used to perform "infinite" research, but the `deeper` command is more user-friendly because most values for the number of `auto` iterations will result in a final output that may cause confusion.

For example, after performing the initial research, running `/research auto 2` will perform one iteration of `more` and one iteration of `combine`. This will result in a report that is based on 2x more sources than the original report. Running `/research auto 3`, however, will perform the two iterations above, plus an additional `more` step. As a result, there will be 3 base reports and 1 combined report, and the final output will be the 3rd base report. While you can still view the combined report by scrolling up or by running `/re view`, this state of affairs is likely to be confusing.

Only certain specific values for the number of `auto` iterations will result in a final output that is a report based on combining all of the previous reports. After doing a bit of math, you can convince yourself that if you only have one base report, then `/research auto 2^N - 2` will result in a report based on 2^(N-1) sources.

But of course, you don't want to have to do math to figure out how many iterations to run. That's why the `deeper` command is more user-friendly. It will automatically figure out how many iterations to run to get a report based on 2x more sources than the current main report.

### The `view` subcommand

Finally, you can view the reports and some stats on them using the `/research view` command. The `/research view stats` command will show the report stats, such as how many sources have been processed, how many base and combined reports there are, etc. The `/research view main` command (`main` is optional) will show the stats and main report, i.e. the report that combines the most sources. The `/research view base` command will show the base reports. The `/research view combined` command will show the combined reports.

## Database Management

You can use the following commands to manage your collections:

- `/db list`: list all your collections
- `/db use my-cool-collection`: switch to the collection named "my-cool-collection"
- `/db rename my-cool-collection`: rename the current collection to "my-cool-collection"
- `/db delete my-cool-collection`: delete the collection named "my-cool-collection"
- `/db`: show database management options

Additional shorthands:

- `/db use 3`: switch to collection #3 in the list
- `/db delete 3, 42, 12`: delete collections #3, #42, and #12 (be careful!)
- `/db delete --current` (or just `-c`): delete the current collection

## Ingesting Documents

To ingest your local documents and use them when chatting with the bot, you can simply type `/ingest` if you are using the Streamlit UI (which is the default way of using the bot). You will then be prompted to upload your documents. You can also ingest a URL by typing `/ingest` followed by the URL. The bot will then retrieve the content of the URL and ingest it into a new collection.

Once the documents are ingested, you can continue adding more documents or URLs by using the `/ingest` command again. When you are done, you should rename the collection (`/db rename new-name`). Why should you rename it? Because if the collection has the default name the system assigned to it, any future use of the `/ingest` command will continue adding documents to it.

Additionally, using the `/research` command automatically ingests the results of the web research into a new document collection.

> The ingestion process for the console mode, which is a bit less streamlined, is described in the [Appendix](#ingesting-documents-in-console-mode).

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

### Ingesting Documents in Console Mode

In the console mode, the ingestion process is currently a bit less convenient than in the (default) Streamlit mode:

#### 1. Fill in the desired ingestion settings in the `.env` file

Set the following values in the `.env` file:

```bash
DOCS_TO_INGEST_DIR_OR_FILE="path/to/my-awesome-data"
COLLECTON_NAME_FOR_INGESTED_DOCS5="my-awesome-collection"
```

#### 2. Run the ingestion script

To ingest the documents, run:

```bash
python ingest_local_docs.py
```

The script will show you the ingestion settings and ask for confirmation before proceeding.

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
