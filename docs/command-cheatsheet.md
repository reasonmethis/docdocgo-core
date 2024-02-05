# Command Cheatsheet

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

Need a clarification about any of the commands? There are two ways to get more help:

1. You can ask DocDocGo for help with using it. Simply type `/help` followed by your question. If the default `docdocgo-documentation` collection is selected you don't even need to use the `/help` prefix.

2. Check out the [README](https://github.com/reasonmethis/docdocgo-core/blob/main/README.md).
