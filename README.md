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
- [FAQ](#faq)
- [Contributing](#contributing)
- [Appendix](#appendix)
  - [Dev FAQ](#dev-faq)
  - [Minified Requirements](#minified-requirements)
  - [Ingesting Documents in Console Mode](#ingesting-documents-in-console-mode)
  - [Running the Containerized Application](#running-the-containerized-application)
  - [License](#license)

## Introduction

DocDocGo is a chatbot that can ingest the content of websites and your local documents and use them in its responses. In other words, it is like ChatGPT with custom knowledge bases built from your documents or from sources it gathers online on your behalf. It comes in two versions: DocDocGo Carbon (commercial, sold to Carbon Inc.) and DocDocGo Core (this repository).

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

If you simply wish to use the bot, you don't need to install it. It is available at [https://docdocgo.streamlit.app](https://docdocgo.streamlit.app). If you would like to run the bot on your local machine, you can follow the instructions below.

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

> Note: if you would like to see a "minified" version of the requirements, please see the [Appendix](#minified-requirements).

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

Ingesting into the current vs a new collection:

- `/ingest new <with or without URL>`: ingest into a new collection
- `/ingest add <with or without URL>`: ingest and add to the current collection
- `/summarize ... URL`: same rules in regards to `new`/`add`

The default behavior (if `new`/`add` is not specified) is to (a) normally ingest into a new collection, which is given a special name (`ingested-content-...`); (b) if the current collection has this kind of name, add to it. That way, you can use `/ingest` several times in a row and all the documents will be added to the same collection.

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
- `/research <cmd> 42`: repeat command such as `more`, `combine`, `iterate`, etc. 42 times
- `/research set-query <your query>`: change your research query
- `/research set-report-type <new report type>`: instructions for the desired report format
- `/research set-search-queries`: perform web searches with new queries and queue up resulting links
- `/research clear`: remove all reports but keep ingested content
- `/research startover`: perform `/research clear`, then rewrite the initial report

You can also view the reports:

- `/research view main`: view the stats and main report (`main` can be omitted)
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
  c. If some adjustments are needed use `/research set-...`, then `/research startover` (see below).
  d. Otherwise, continue to step 3.
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

You can view the reports and some basic info on them using the `/research view` command. The `/research view stats` command will show the report basic info, such as the query and report type, as well as report stats, such as how many sources have been processed, how many base and combined reports there are, etc. The `/research view main` command (`main` is optional) will show the stats and main report, i.e. the report that combines the most sources. The `/research view base` command will show the base reports. The `/research view combined` command will show the combined reports.

### The `set-...` subcommands

If you are not quite happy with how the report is shaping up, you have the option to change the focus and/or the format of the report, without having to re-fetch and re-ingest the already ingested websites. The `/research set-query` command allows you to change the query for the current research. The `/research set-report-type` command allows you to change the report format. The `/research set-search-queries` command allows you to specify new web search queries DocDocGo will use to fetch more content from the web.

What are the query and report format? The query is just what you specified in your initial `/research <query>` command. The report format is originally automatically inferred by DocDocGo based on your query, but you can change it a new format. For example, you can request:

```markdown
/research set-report-type Numbered list with short bullet points and URL of corresponding source
```

All subsequent reports will be generated using the new query, format, and/or search queries. Here are a couple of possible (but not the only) workflows:

1. Changing the query and/or report type, followed by the `startover` command (which we'll discuss next).
2. Changing the search queries and continuing without starting over, using commands such as `deeper`, `auto`, `iterate`, etc.

### The `clear` and `startover` subcommands

The `/research clear` command will remove all reports but keep the ingested content. The `/research startover` command will perform the `/research clear` command, then rewrite the initial report. This is useful if you want to change the query and/or report format, but don't want to re-ingest the already ingested websites. Rewriting the reports without having to re-fetch and re-ingest the websites makes things go much faster and is especially useful if you have already accumulated a lot of relevant content.

## Database Management

You can use the following commands to manage your collections:

- `/db list`: list all your collections
- `/db use my-cool-collection`: switch to the collection named "my-cool-collection"
- `/db rename my-cool-collection`: rename the current collection to "my-cool-collection"
- `/db delete my-cool-collection`: delete the collection named "my-cool-collection"
- `/db status`: show your access level for the current collection and related info
- `/db`: show database management options

Additional shorthands:

- `/db use 3`: switch to collection #3 in the list
- `/db delete 3, 42, 12`: delete collections #3, #42, and #12 (be careful!)
- `/db delete --current` (or just `-c`): delete the current collection

## Ingesting Documents

To ingest your local documents and use them when chatting with the bot, you can simply type `/ingest` if you are using the Streamlit UI (which is the default way of using the bot). You will then be prompted to upload your documents. You can also ingest a URL by typing `/ingest` followed by the URL. The bot will then retrieve the content of the URL and ingest it into a new collection.

Once the documents are ingested, you can continue adding more documents or URLs by using the `/ingest` command again. When you are done, you should rename the collection (`/db rename new-name`).

You can also explicitly control whether the documents are ingested into a new collection or added to the current collection. To ingest into a new collection, use `/ingest new`. To add to the current collection, use `/ingest add`. See [Using DocDocGo](#using-docdocgo) for more details.

The `/summarize` command works similarly to the `/ingest` command, but it retrieves the content of the URL and summarizes it before ingesting it into a collection.

Additionally, using the `/research` command automatically ingests the results of the web research into a new document collection.

> The ingestion process for the console mode, which is a bit less streamlined, is described in the [Appendix](#ingesting-documents-in-console-mode).

## Sharing your collection with others

If you have owner-level access, you can use the following commands to share the current collection with others:

- `/share viewer pwd <any letters or numbers>`: give viewer access to the current collection
- `/share editor pwd <any letters or numbers>`: give editor access to the current collection
- `/share owner pwd <any letters or numbers>`: give owner access to the current collection

You can also revoke access:

- `/share revoke pwd <any letters or numbers>`: revoke a specific access code
- `/share revoke all-pwds`: revoke all access codes
- `/share revoke user <user ID>`: revoke access for a specific user
- `/share revoke all-users`: revoke access for all users
- `/share delete ...`: same as `revoke`

What is the difference between _viewer_, _editor_, and _owner_?

- _viewer_ can interact with the collection only in a way that does not modify it. For example, they can ask questions about its contents.
- _editor_ can perform actions that modify the contact collection, for example by ingesting new documents into it. They can't, however, rename, delete, or share the collection.
- _owner_ has unrestricted access to the collection

After you enter your command as described above, you will get a link that you can share with others. If you go with the `pwd` option, the recipient will always need to use that link to access the collection. If you opt for the `unlock-code` option (not yet implemented), the recipient will only need to use the link once, and then they will be able to access the collection without it.

**Tip:** If you have owner access to a collection, you can use `/db status` to see the access level of other users.

## Querying based on substrings

DocDocGo allows you to query your documents simultaneously based on the meaning of your query and on keywords (or any substrings) in the documents. To do this, simply include the substrings in your query, enclosed in quotes. For example, if your message is:

```markdown
When is "Christopher" scheduled to attend the conference?
```

DocDocGo will only consider document chunks that contain the substring "Christopher" when answering your query.

## FAQ

This section provides answers to frequently asked questions for using DocDocGo. For development-related questions, please see the [Dev FAQ](#dev-faq) in the Appendix.

### Accessing collections

#### Q: I entered my own OpenAI API key and now can't see collections I saw before. What happened?

A: Before you entered your own OpenAI API key, you were using the community key and could see and create public collections (accessible to everyone). After entering your own key, collections you create are private to you, and running `/db list` will only show your own collections.

You still have access to the public collections, you can switch to any public collection by typing `/db use <collection name>`. If you want to see all available public collections again, you can switch back to the community key by simply deleting the key you entered and pressing Enter, then running `/db list` again.

#### Q: I got a shareable link to a collection but using it reloads the app, so it ends up in its default state of using the community key. How can I use the link with my own OpenAI API key?

A: Simply enter your key in the OpenAI API key field after the app has reloaded. The access code will still be valid.

## Contributing

Contributions are welcome! If you have any questions or suggestions, please open an issue or a pull request.

## Appendix

### Dev FAQ

Here we provide additional information that may be useful, mostly for developers, as opposed to users of the bot.

#### Q: How can I update the default collection?

A: You can do it in two steps:

1. Ingest the new content into a new collection using the `/ingest` command.
2. Rename the new collection to `docdocgo-documentation` using the special admin command `/db rename --default <value of the BYPASS_SETTINGS_RESTRICTIONS_PASSWORD environment variable>`.

#### Q: I want to fork this repository and use a vector database on my local machine. How do I make sure that when I pull updates from the original repository, I don't overwrite my local database?

A: The easiest way is to set:

```env
VECTORDB_DIR="some-custom-dir-name-outside-of-project-dir/" # directory of your doc database
```

That way you don't have to worry about the `chroma/` directory being freshly pulled from this repo. To make sure your custom directory contains the default collection `docdocgo-documentation`, which is what the `chroma/` directory contains initially, you should be able to simply copy the contents of `chroma/` to your chosen custom directory.

As an alternative way to handle the issue of the default collection, you can create your own version of the default collection by ingesting this README, along with any other files you wish to be included. To make the resulting collection the default collection, use the command `/db rename --default <admin pwd you set>`, where the admin password is the value you assigned to the `BYPASS_SETTINGS_RESTRICTIONS_PASSWORD` environment variable.

#### Q: What is the `BYPASS_SETTINGS_RESTRICTIONS` environment variable?

A: Normally, when this variable is not defined (or is an empty string), the app will start in a "community key" mode, where you can only see and create public collections and there are restriction on allowed settings (e.g. you can't change the model in the UI). The key used as the community key is controlled by the `DEFAULT_OPENAI_API_KEY` environment variable. You can remove these restrictions and switch to using that same key as a private key by entering the admin password (the value of the `BYPASS_SETTINGS_RESTRICTIONS_PASSWORD` environment variable) in rhe OpenAI API key field.

However, when the `BYPASS_SETTINGS_RESTRICTIONS` variable is set to a non-empty string, the app will start in the "private key" mode right away, without you having to enter the admin password. This is useful if you use the app in a private setting and don't want to have to enter the admin password every time you start the app.

### Minified Requirements

Installing the following packages will also install all of the other requirements:

```bash
langchain==0.1.6
langchain_openai==0.0.5
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
icecream==2.1.3
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
