# DocDocGo

DocDocGo is a multifunctional chatbot that saves you time when you have to sift through lots of websites or documents to find the information you need.

![version](https://img.shields.io/badge/version-v0.2.5-blue.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://docdocgo.streamlit.app)

## Table of Contents

- [Introduction](#introduction)
- [(Very) Quickstart](#very-quickstart)
- [Installation](#installation)
- [Running DocDocGo](#running-docdocgo)
- [Using DocDocGo](#using-docdocgo)
- [Research Commands](#research-commands)
- [Database Management](#database-management)
- [Ingesting Documents](#ingesting-documents)
- [Exporting data](#exporting-data)
- [Sharing your collection with others](#sharing-your-collection-with-others)
- [Querying based on substrings](#querying-based-on-substrings)
- [FAQ](#faq)
- [DocDocGo Carbon](#docdocgo-carbon)
- [Contributing](#contributing)
- [License](#license)

## Introduction

DocDocGo is a research assistant and a RAG chatbot in one. It addresses the common problem of spending too much time manually searching through multiple sources to find the information you need.

In its **heatseek mode**, it will happily sift through dozens or hundreds of websites to find the answer to a specific narrow question. If the kind of information you are looking for is not easily found on the first page of Google search results, ask DocDocGo to find it for you while you enjoy a cup of coffee.

In its **classic research mode**, DocDocGo will similarly find more and more sources on the topic you give it, but this time it will ingest them into a knowledge base (called _collection_) and generate a report that _combines insights_ from all sources. You can then chat with the collection, asking any follow-up questions and getting answers based on all ingested information.

You can do lots more with DocDocGo:

- ingest your own documents into a new or existing collection and chat with them
- share your collection with others, giving them viewer, editor, or owner access
- manually set the Google search queries to use when conducting research
- explicitly specify the report format you want to use
- summarize and ingest a given URL into a new or existing collection
- query your collection based simultaneously on semantics and on substrings in the documents
- export your conversation to a text file
- get direct quotes from the documents in your collection relevant to your query
- manage your collections, e.g. rename, delete, or switch between them
- access it via a convenient Streamlit UI or its FastAPI server

On top of that, DocDocGo is **"self-aware"** - it can answer questions about its own capabilities and provide help with using all of its features. Because of this, the only command you need to remember is `/help` - for example, you can ask it something like this:

```markdown
/help Is there a way to create a shareable link to a collection and set the access level to read-only?
```

## (Very) Quickstart

You will see more detailed setup instructions below, but here they are in a nutshell:

1. Install requirements with `pip install -r requirements.txt`
2. Create `.env` using `.env.example`
3. Run `streamlit run streamlit_app.py`

That's it, happy chatting!

## Installation

If you simply wish to use the bot, you don't need to install it. It is available at [https://docdocgo.streamlit.app](https://docdocgo.streamlit.app). If you would like to run the bot on your local machine, you can follow the instructions below.

If you want to build with DocDocGo, you will likely want to check out the [Developer Guide](https://github.com/reasonmethis/docdocgo-core/blob/main/README-FOR-DEVELOPERS.md) for more detailed information on how to work with DocDocGo from a developer's perspective. Among other things, it explains [how to work with the DocDocGo FastAPI server](https://github.com/reasonmethis/docdocgo-core/blob/main/README-FOR-DEVELOPERS.md#using-the-fastapi-server) and has an [FAQ](https://github.com/reasonmethis/docdocgo-core/blob/main/README-FOR-DEVELOPERS.md#faq) for miscellaneous questions. A likely even better way to get your development-related questions answered is to ask DocDocGo itself! Simply switch to the `developer-docs` collection by typing `/db use developer-docs` and then ask your question.

### 1. Clone this repository and cd into it

```bash
git clone https://github.com/reasonmethis/docdocgo-core.git
cd docdocgo-core
```

### 2. Create and activate a virtual environment

First, make sure you are using Python 3.11 or higher. Then, create a virtual environment and activate it.

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

DocDocGo also comes with a FastAPI server, which can be run with:

```bash
uvicorn api:app --reload
```

or by running `api.py` directly.

The details of using the API are described in the [Developer Guide](https://github.com/reasonmethis/docdocgo-core/blob/main/README-FOR-DEVELOPERS.md#using-the-fastapi-server). The API was used in the commercial version of DocDocGo to interact with the accompanying Google Chat App. It can be similarly used to integrate DocDocGo into any other chat application, such as a Telegram or Slack bot.

## Using DocDocGo

Now let's go over my features and commands. The general pattern for queries is to enter one of the prefixes below followed by your message. Different prefixes activate my different capabilities. A prefix is optional - messages with no prefix by default get treated as regular chat using the current collection as a knowledge base.

Here's what each prefix does. Most important ones:

- `/kb <your query>`: chat using the current collection as a knowledge base
- `/research <your query>`: do "classic" research - ingest websites into a collection, write a report
- `/research heatseek <your query>`: do "heatseek" research - find websites that contain the answer
- `/ingest`: upload your documents and ingest them into a collection
- `/ingest https://some.url.com`: retrieve a URL and ingest into a collection
- `/summarize https://some.url.com`: retrieve a URL, summarize and ingest into a collection
- `/db`: manage your doc collections (select, rename, etc.)
- `/share`: share your collection with others
- `/help <your query>`: get help with using DocDocGo

Other prefixes:

- `/details <your query>`: get details about the retrieved documents
- `/quotes <your query>`: get quotes from the retrieved documents
- `/web <your query>`: perform web searches and generate a report without ingesting
- `/chat <your query>`: regular chat, without retrieving docs or websites
- `/export`: export your data

Ingesting into the current vs a new collection:

- `/ingest new <with or without URL>`: ingest into a new collection
- `/ingest add <with or without URL>`: ingest and add to the current collection
- `/summarize <new/add> <URL>`: same rules in regards to `new`/`add`

The default behavior (if `new`/`add` is not specified) is to (a) normally ingest into a new collection, which is given a special name (`ingested-content-...`); (b) if the current collection has this kind of name, add to it. That way, you can use `/ingest` several times in a row and all the documents will be added to the same collection.

Example queries:

- `/help What in the world is infinite research?`
- `/research What are this month's most important AI news?`
- `/research` (to see research options)
- `/research deeper` (to expand the research to cover more sources)
- `/re deeper` (same - first two letters of a command are enough)
- `/kb Which news you found relate to OpenAI`
- `/chat Reformat your previous answer as a list of short bullet points`
- `/re heatseek 3 I need example code for how to update React state in shadcn Slider component`

We'll delve into the most important commands in more detail in the sections below. Another way to get help is to simply ask DocDocGo itself. Simply type `/help` followed by your question. If the default `docdocgo-documentation` collection is selected you don't even need to use the `/help` prefix.

## Research Commands

There are now two modes of research: "heatseek" (for finding just that perfect website) and "classic" (for compiling information from multiple websites). Let's first provide a "cheatsheet" of all of the research options, and then go over them individually and provide more detailed information.

> _KB_ stands for _knowledge base_, also known as a _collection_.

### Overview

Here are the most important commands you can use for DocDocGo's signature "infinite" research:

**1. Heatseek mode:** look for websites that contain the answer to your query (no KB created)

- `/research heatseek 6 <your query>`: perform 6 rounds of "heatseek" research
- `/re hs 5`: perform 5 more rounds (can use shorthands for commands)

This is a newer, more lightweight mode that is highly useful when you need to find that "gem" of a website that contains some specific information and Google is just giving you too much noise.

**2. Classic mode:** use content from multiple websites to write a detailed answer, create a KB

- `/research <your query>`: start new research, generate report, create KB from fetched sites
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

> To save keystrokes, you can use the shorthand `/re` instead of `/research`.

Let's go over the commands in more detail to get a better understanding of what they do and the differences between them.

### The `heatseek` mode

The `/re heatseek` command is a newer, easy-to-use mode of research that doesn't try to compile information from multiple sources (as the regular mode does), but instead focuses on finding the perfect website that contains the answer to your query.

You might ask - why not just use Google (or perhaps Perplexity)? The answer is that you in fact _should_ start with just a regular web search, and you may very well find what you need quickly. But sometimes you don't, and you need to dig deeper: go beyond the first page of search results, try different search queries, read through multiple websites, etc. `/research heatseek` automates all of this for you! For example, you can type:

```markdown
/re heatseek 3 Find code snippet that shows how to update React state in shadcn Slider component
```

and watch as DocDocGo fetches websites, reads through them, and tries to find one that contains what you asked for. If it doesn't find it in the first round, it will try again, and again, up to the number of rounds you specify. In the example above, it will do 3 rounds, and if you don't specify a number, it will default to one round.

If you would like to do more rounds after the initial command finishes, you can type:

```markdown
/re hs <number of rounds>
```

and it will perform the specified number of additional rounds. Note that you can always use the shorthand `hs` instead of `heatseek`, just as you can use `re` instead of `research`.

Now let's go over the subcommands for the classic research mode.

### The `iterate` subcommand

Assuming you have already initiated your research using `/re <your query>`, if you then type `/re iterate`, DocDocGo will fetch more content from the web and use it to try to improve its initial report. If you type `/re iterate N`, DocDocGo will automatically do `N` repetitions of the `/research iterate` command. Each repetition will fetch more content related to your original query and produce a new version of the report. All fetched content will be added to a KB (aka _collection_) for any follow-up questions.

> If you are doing multiple iterations and want to abort, simply reload the UI.

### The `deeper` subcommand

The above approach sounds neat, but it doesn't always work in practice, especially if you use a not-so-smart model, like GPT-3.5. Specifically, it sometimes treats the information from the latest small batch of sources on an equal or higher footing than the information in the pre-existing report, even when the latter is based on many more sources and thus should be prioritized. Important information can then be lost and the report can become worse after a new iteration, not better.

That's why we have the `/research deeper` command. Instead of using new sources to try to directly improve the report, it uses a combination of `more` and `combine` operations to generate _separate_ reports from additional sources and then combine them with the existing report(s) in a way that doesn't unfairly prioritize the new sources. Each run of the `/re deeper` command will double the number of sources in the report.

> As always, all fetched content will be added to the collection for follow-up chat.

### The recommended workflow for classic research

The "infinite" research capability of DocDocGo comes from the ability to automatically perform multiple repetitions of the `deeper` command (and other research commands). Simply run `/re deeper N`, where `N` is a number, to automatically run the `deeper` command `N` times, each time doubling the number of sources. Setting `N` to 5, for example, will result in a report that is based on 32x more sources than the initial report (around 200). This will take a while, of course, and you can abort at any time by reloading the app.

Here's a basic workflow for research:

1. Start with `/re <your query>` to generate a report based on the initial sources.
2. Decide on the next step:  
   a. If you are happy with the report, you can stop here.  
   b. If the report is completely off, you can go back to step 1 and try a new query.  
   c. If some adjustments are needed, use one of the `/re set-...` commands (see below), then `/re startover`.
   d. Otherwise, continue to step 3.
3. Use `/re deeper N` to perform `N` iterations of the `deeper` command. Don't set `N` too high, since every such iteration **doubles** the number of sources in the report.
4. Ask any follow-up questions you have.

> For most use cases, this workflow will more than suffice, and you don't need to use the `iterate`, `auto`, `more` or `combine` subcommands. The `deeper` subcommand (with the occasional`/re set-...` commands for adjustments) is the most user-friendly way to perform "infinite" research.

### The `more` and `combine` subcommands

> Note: The `more` and `combine` subcommands are not part of the basic research workflow. They are meant for advanced users who need more control over the research process.

What are these `more` and `combine` operations? `/re more` allows you to fetch more content from the web and generate a _separate_ report, without affecting the original report. This is useful if you want to see what else is out there, but don't want to risk messing up the original report.

Such separate reports are called _base reports_. If you'd like to combine the most important information from two base reports into one report, you can use the `/re combine` command. It will automatically find the two highest-level reports (at the same level) that haven't been combined yet and combine them. "Level" here roughly corresponds to the number of sources that went into the report. More precisely, base reports have level 0. When two reports are combined, the level of the new report is 1 higher than the level of the two reports that were combined.

### The `auto` subcommand

> Note: The `auto` subcommand is not part of the basic research workflow. It is meant for advanced users who need more control over the research process.

The `/research auto` command is a combination of the `/re more` and `/re combine` commands. It automatically selects one or the other. If there are reports to combine, it will use the `/re combine` command. Otherwise, it will use the `/re more` command to fetch more content from the web and generate a new base report.

You can request multiple iterations of this command. For example, `/re auto 42` will automatically perform 42 iterations of `/re auto`. (To abort, simply reload the app.)

You can add a number to the end of the `/re more` and `/re combine` commands as well to repeat them multiple times.

### Understanding the `deeper` command and its relation to `auto`

Both `deeper` and `auto` can be used to perform "infinite" research, but the `deeper` command is more user-friendly because most values for the number of `auto` iterations will result in a final output that may cause confusion.

For example, after performing the initial research, running `/re auto 2` will perform one iteration of `more` and one iteration of `combine`. This will result in a report that is based on 2x more sources than the original report. Running `/re auto 3`, however, will perform the two iterations above, plus an additional `more` step. As a result, there will be 3 base reports and 1 combined report, and the final output will be the 3rd base report. While you can still view the combined report by scrolling up or by running `/re view`, this state of affairs is likely to be confusing.

Only certain specific values for the number of `auto` iterations will result in a final output that is a report based on combining all of the previous reports. After doing a bit of math, you can convince yourself that if you only have one base report, then `/re auto 2^N - 2` will result in a report based on 2^(N-1) sources.

But of course, you don't want to have to do math to figure out how many iterations to run. That's why the `deeper` command is more user-friendly. It will automatically figure out how many iterations to run to get a report based on 2x more sources than the current main report.

### The `view` subcommand

You can view the reports and some basic info on them using the `/re view` command. The `/re view stats` command will show the report basic info, such as the query and report type, as well as report stats, such as how many sources have been processed, how many base and combined reports there are, etc. The `/re view main` command (`main` is optional) will show the stats and main report, i.e. the report that combines the most sources. The `/re view base` command will show the base reports. The `/re view combined` command will show the combined reports.

### The `set-...` subcommands

If you are not quite happy with how the report is shaping up, you have the option to change the focus and/or the format of the report, without having to re-fetch and re-ingest the already ingested websites. The `/re set-query` command allows you to change the query for the current research. The `/re set-report-type` command allows you to change the report format. The `/re set-search-queries` command allows you to specify new web search queries DocDocGo will use to fetch more content from the web.

What are the query and report format? The query is just what you specified in your initial `/re <query>` command. The report format is originally automatically inferred by DocDocGo based on your query, but you can change it to a new format. For example, you can type:

```markdown
/re set-report-type Numbered list with short bullet points and URL of corresponding source
```

All subsequent reports will be generated using the new query, format, and/or search queries. Here are a couple of possible (but not the only) workflows:

1. Changing the query and/or report type, followed by the `startover` command (which we'll discuss next).
2. Changing the search queries and continuing without starting over, using commands such as `deeper`, `auto`, `iterate`, etc.

### The `clear` and `startover` subcommands

The `/re clear` command will remove all reports but keep the ingested content. The `/re startover` command will perform the `/re clear` command, then rewrite the initial report. This is useful if you want to change the query and/or report format, but don't want to re-ingest the already ingested websites. Rewriting the reports without having to re-fetch and re-ingest the websites makes things go much faster and is especially useful if you have already accumulated a lot of relevant content.

## Database Management

You can use the following commands to manage your collections:

- `/db list`: list all your collections
- `/db list bla`: list your collections whose names contain "bla"
- `/db use my-cool-collection`: switch to the collection named "my-cool-collection"
- `/db rename my-cool-collection`: rename the current collection to "my-cool-collection"
- `/db delete my-cool-collection`: delete the collection named "my-cool-collection"
- `/db status`: show your access level for the current collection and related info
- `/db`: show database management options

Additional shorthands:

- `/db use 3`: switch to collection #3 in the list
- `/db list 42+`: list collections starting from #42
- `/db list bla*`: list collections whose names start with "bla"
- `/db delete 3, 42, 12`: delete collections #3, #42, and #12 (be careful!)
- `/db delete --current` (or just `-c`): delete the current collection

## Ingesting Documents

### Ingesting local documents

To ingest your local documents and use them when chatting with the bot, you can simply type `/ingest`. If you are using the Streamlit UI, the uploader widget will appear and you'll be able to select one or more files to upload.

If you are using a different UI, what happens after you type `/ingest` can be somewhat different but should still provide you with a way to select and upload your documents.

### Ingesting URLs

You can also ingest a URL by typing `/ingest` followed by the URL. The bot will then retrieve the content of the URL and ingest it into a new collection.

### Ingesting further content

Once the documents are ingested, you can continue adding more documents or URLs by using the `/ingest` command again. When you are done, you should rename the collection (`/db rename new-name`).

You can also explicitly control whether the documents are ingested into a new collection or added to the current collection. To ingest into a new collection, use `/ingest new <URL>`. To add to the current collection, use `/ingest add <URL>`. See [Using DocDocGo](#using-docdocgo) for more details.

### Summarizing local documents or URLs

The `/summarize` command works similarly to the `/ingest` command, except, in addition to ingesting the content of the URL it also generates a summary of the content (the summary is not itself ingested).

## Exporting data

To export your conversation, use the command:

- `/ex chat <optional number of past messages>` (or `/export` instead of `/ex`)

If the number of past messages is not specified, the entire conversation will be exported. If you want to export the messages in reverse order, use `/ex <optional number> reverse`.

## Sharing your collection with others

If you have owner-level access to the current collection, you can use the following commands to share it with others:

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
- _editor_ can perform actions that modify the collection, for example by ingesting new documents into it. They can't, however, rename, delete, or share the collection.
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

This section provides answers to frequently asked questions about using DocDocGo.

### Accessing collections

#### Q: I entered my own OpenAI API key and now can't see collections I saw before. What happened?

A: Before you entered your own OpenAI API key, you were using the community key and could see and create public collections (accessible to everyone). After entering your own key, collections you create are private to you, and running `/db list` will only show your own collections.

You still have access to the public collections, you can switch to any public collection by typing `/db use <collection name>`. If you want to see all available public collections again, you can switch back to the community key by changing the key to an empty string, then running `/db list` again.

#### Q: I got a shareable link to a collection but using it reloads the Streamlit app, after which it ends up in its default state of using the community key. How can I use the link with my own OpenAI API key?

A: Simply enter your key in the OpenAI API key field after the app has reloaded. The access code will still be valid.

## DocDocGo Carbon

DocDocGo Carbon (not available here) is the original incarnation of DocDocGo and is licensed to [Carbon Inc.](https://www.carbon3d.com/). It has the following features:

- It is integrated with a Google Chat App
- Interacts with the client company's Confluence documentation
- Offers the ability to provide feedback on the quality of its responses
- Has a database for conversations and feedback and allows to resume the conversation

## Contributing

Contributions are welcome! If you have any questions or suggestions, please open an issue or a pull request.

## License

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
