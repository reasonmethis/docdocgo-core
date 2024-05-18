# Developer Documentation

Here we provide information useful for developers who want to build on top of DocDocGo or contribute to its development. 

> An alternative way to get your development-related questions answered is to ask DocDocGo itself! Simply switch to the `developer-docs` collection by typing `/db use developer-docs` and then ask your question.

## Table of Contents

- [Installation](#installation)
- [Using the FastAPI server](#using-the-fastapi-server)
- [Ingesting Documents in Console Mode](#ingesting-documents-in-console-mode)
- [Running the FastAPI server in Docker](#running-the-fastapi-server-in-docker)
- [FAQ](#faq)

## Installation

If you simply wish to use the bot, you don't need to install it. It is available at [https://docdocgo.streamlit.app](https://docdocgo.streamlit.app). If you would like to run the bot on your local machine, you can follow the instructions below.

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

The details of using the API are described in the [Using the FastAPI Server](#using-the-fastapi-server) section. The API was used in the commercial version of DocDocGo to interact with the accompanying Google Chat App. It can be similarly used to integrate DocDocGo into any other chat application, such as a Telegram or Slack bot.

## Using the FastAPI server

The FastAPI server is a RESTful API that can be used to interact with DocDocGo programmatically. The following endpoints are available:

- `/chat`: send a message to the bot
- `/ingest`: send files to the bot with or without a message

### The `/chat` endpoint

The `/chat` endpoint is used to send a message to the bot. The API works similarly to, e.g., the OpenAI API in the sense that it's stateless. For example, since the server doesn't "remember" the previous chat history, you are welcome to send either the actual or completely made up chat history.

Before we dive in to the details of using the API, note that you can find a reference implementation of a client in the form of a Next.js frontend. The code can be found [here](https://github.com/reasonmethis/docdocgo-nextjs-basic) and can be used to clarify usage details, if you would like to build your own client.

### 1. The request

The message should be sent as a POST request with the body as a JSON object that corresponds to the following schema:

```python
class ChatRequestData(BaseModel):
    message: str
    api_key: str
    openai_api_key: str | None = None
    chat_history: list[JSONish] = []
    collection_name: str | None = None
    access_codes_cache: dict[str, str] | None = None  # coll name -> access_code
    scheduled_queries_str: str | None = None  # JSON string of ScheduledQueries
```

The chat history (which represents what you would like the bot to assume has been said before) should be in the following format:

```json
[
    {
        "role": "user",
        "content": "Hello, how are you?"
    },
    {
        "role": "assistant",
        "content": "I'm doing well, thank you. How can I help you today?"
    },
    {
        "role": "user",
        "content": "/research What are the most important AI news this month?"
    }
]
```

The `collection_name` field is used to specify the collection that the bot should use when responding to the message. If not specified, the default collection will be used. The optional `access_code` field is used to specify the access code for the collection. The bot will determine your access level and respond accordingly.

The `api_key` field is used to specify the API key for the FastAPI server. The server will only honor requests that include the correct API key, as specified by the `DOCDOCGO_API_KEY` environment variable in.

The `openai_api_key` field is used to specify the OpenAI API key. If not specified, the default (community) key will be used, assuming the `DEFAULT_OPENAI_API_KEY` environment variable is set.

The `access_codes_cache` field is an object mapping collection names to access codes that the client has stored for them for the current user. The bot will use these access codes to determine grant the user access to collections that require it.

Where is the client supposed to get these access codes from? Any relevant access codes will have been provided to the client in the responses to previous requests (see the response schema below) with the `INSTRUCT_CACHE_ACCESS_CODE` instruction.

Where does the bot get these access codes from? They are extracted from shareable links that the user provides via the URL query parameters or when the user runs a `/db use <shareable-link>` command.

The `scheduled_queries_str` field is a string that encodes a data structure holding information about what queries the bot should auto-run next. The details of this data structure are not necessary to understand from the perspective of the client of the API because the client simply needs to pass the string that was received from the bot in the previous response (or not pass it at all if the bot didn't provide it).

> If some of these details are unclear, remember that you can see a fully functional example of a Next.js frontend that uses the API [here](https://github.com/reasonmethis/docdocgo-nextjs-basic).

### 2. The response

The response will be a JSON object conforming to the following schema:

```python
class ChatResponseData(BaseModel):
    content: str
    sources: list[str] | None = None
    collection_name: str | None = None
    user_facing_collection_name: str | None = None
    instructions: list[Instruction] | None = None
    scheduled_queries_str: str | None = None  # JSON string of ScheduledQueries
```

where `Instruction` is defined as:

```python
INSTRUCT_SHOW_UPLOADER = "INSTRUCT_SHOW_UPLOADER"
INSTRUCT_CACHE_ACCESS_CODE = "INSTRUCT_CACHE_ACCESS_CODE"

class Instruction(BaseModel):
    type: str # one of the above constants
    user_id: str | None = None
    access_code: str | None = None
```

The `content` field is the message from the bot. The `sources` field, if provided, is a list of sources used to generate the reply, e.g. the URLs of the previously ingested websites or names of the previously ingested local documents. The `collection_name` field is the name of the current collection.

Finally, the `scheduled_queries_str` is a string that encodes a data structure holding information about what queries the bot should auto-run next. The details of this data structure are not necessary to understand from the perspective of the client of the API because the client simply needs to pass it back to the bot in the next request.

> If some of these details are unclear, remember that you can see a fully functional example of a Next.js frontend that uses the API [here](https://github.com/reasonmethis/docdocgo-nextjs-basic).

### The `/ingest` endpoint

The `/ingest` endpoint is used to send files to the bot, with or without message. The bot will ingest the files into a collection in the same way as during the [`/ingest` command in the Streamlit mode](README.md#ingesting-local-documents). The data should be sent as a POST request with the body being form data that corresponds to the following schema:

```python
async def ingest(
    files: Annotated[list[UploadFile], File()],
    message: Annotated[str, Form()],
    api_key: Annotated[str, Form()],
    openai_api_key: Annotated[str | None, Form()] = None,
    chat_history: Annotated[str | None, Form()] = None,  # JSON string
    collection_name: Annotated[str | None, Form()] = None,
    access_codes_cache: Annotated[str | None, Form()] = None,  # JSON string
    scheduled_queries_str: Annotated[str | None, Form()] = None, # JSON string of ScheduledQueries
):
```

Except for the `files` field, all fields are the same as in the `/chat` endpoint. The `files` field is a list of file objects that the client wants to ingest.

> For an example of how to send files, see the [reference frontend implementation](https://github.com/reasonmethis/docdocgo-nextjs-basic).

What happens if a non-empty `message` field is provided? The bot will treat the message as if it was sent by the user after the files were uploaded. It will ingest the files, parse the message, add it to `scheduled_queries_str` and return without responding to the message but with the understanding that the frontend should pass that same value back in the next request, at which point the scheduled query will be executed. This is done because the API is designed to be stateless and to process one query or command at a time in order to avoid long-running requests.

## Ingesting Documents in Console Mode

In the console mode, the ingestion process is currently a bit less convenient than in the (default) Streamlit mode:

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

## Running the FastAPI server in Docker

The following steps can be used to run the containerized FastAPI server.

### 1. Build the Docker image

```bash
docker build -t docdocgo-fastapi .
```

### 2. Run the Docker container

Run the Docker container and expose port 8000:

```bash
docker run --name docdocgo -p 8000:80 docdocgo-fastapi:latest
```

## FAQ

### Q: How can I update the default collection?

A: You can do it in two steps:

1. Ingest the new content into a new collection using the `/ingest` command.
2. Rename the new collection to `docdocgo-documentation` using the special admin command `/db rename --default <value of the BYPASS_SETTINGS_RESTRICTIONS_PASSWORD environment variable>`.

### Q: I want to fork this repository and use a vector database on my local machine. How do I make sure that when I pull updates from the original repository, I don't overwrite my local database?

A: The easiest way is to set:

```env
VECTORDB_DIR="some-custom-dir-name-outside-of-project-dir/" # directory of your doc database
```

That way you don't have to worry about the `chroma/` directory being freshly pulled from this repo. To make sure your custom directory contains the default collection `docdocgo-documentation`, which is what the `chroma/` directory contains initially, you should be able to simply copy the contents of `chroma/` to your chosen custom directory.

As an alternative way to handle the issue of the default collection, you can create your own version of the default collection by ingesting this README, along with any other files you wish to be included. To make the resulting collection the default collection, use the command `/db rename --default <admin pwd you set>`, where the admin password is the value you assigned to the `BYPASS_SETTINGS_RESTRICTIONS_PASSWORD` environment variable.

### Q: What is the `BYPASS_SETTINGS_RESTRICTIONS` environment variable?

A: Normally, when this variable is not defined (or is an empty string), the app will start in a "community key" mode, where you can only see and create public collections and there are restriction on allowed settings (e.g. you can't change the model in the UI). The key used as the community key is controlled by the `DEFAULT_OPENAI_API_KEY` environment variable. You can remove these restrictions and switch to using that same key as a private key by entering the admin password (the value of the `BYPASS_SETTINGS_RESTRICTIONS_PASSWORD` environment variable) in rhe OpenAI API key field.

However, when the `BYPASS_SETTINGS_RESTRICTIONS` variable is set to a non-empty string, the app will start in the "private key" mode right away, without you having to enter the admin password. This is useful if you use the app in a private setting and don't want to have to enter the admin password every time you start the app.

### Q: I want to add a new command to the bot. How do I do that?

A: Here is a high-level overview of the steps you need to take. The links to the code are GitHub permalinks - they always point to the intended part of the codebase but may not show the most recent version of the code.

There are several moving pieces to make a new command. The first stage is parsing a command, which is done [here](https://github.com/reasonmethis/docdocgo-core/blob/4d85a01413f69d7f9198b785075ca1c0835749f0/utils/query_parsing.py#L355). To get your command to be parsed you would need to add a [`ChatMode` Enum](https://github.com/reasonmethis/docdocgo-core/blob/4d85a01413f69d7f9198b785075ca1c0835749f0/utils/type_utils.py#L17) value for it and what [slash command(s)](https://github.com/reasonmethis/docdocgo-core/blob/4d85a01413f69d7f9198b785075ca1c0835749f0/utils/helpers.py#L31) correspond to it.

Then you would need to write logic for how the string following "/your-command" should be parsed and converted into a `ParsedQuery` object. You would add it [here](https://github.com/reasonmethis/docdocgo-core/blob/4d85a01413f69d7f9198b785075ca1c0835749f0/utils/query_parsing.py#L386). You may also want to update the `ParsedQuery` class to be able to hold information about your command (such as the subcommand(s), any provided settings extracted by your parsing logic, basically any data you want to store there to fully represent the command).

Finally, you would add the logic to handle your parsed command by adding another "elif" [here](https://github.com/reasonmethis/docdocgo-core/blob/4d85a01413f69d7f9198b785075ca1c0835749f0/docdocgo.py#L42).
