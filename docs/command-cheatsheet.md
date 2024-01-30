# Command Cheatsheet

You can enter your messages with or without a prefix. Different prefixes activate different response modes.
By default, if a message is entered with no prefix, the `/docs` mode is used.

Here's what each prefix does. Most important prefixes:

- `/research`: perform "infinite" Internet research, ingesting websites into a collection
- `/ingest` or `/upload`: upload your documents and ingest them into a collection
- `/docs <your query>`: chat with me about your currently selected doc collection (or a general topic)
- `/db`: manage your doc collections (select, rename, etc.)

Other prefixes:

- `/help`: show this help message
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

If you're in a reading mood, here's a [link to the full docs](https://github.com/reasonmethis/docdocgo-core/blob/main/README.md).

You can also ask DocDocGo for help with using it. By default, it's set up to use the `docdocgo-documentation` collection, which contains its docs. As long as this collection is selected (as shown in the chat box), it can answer questions about how to use it. And if it's not selected, you can switch to it with `/db use 1`.
