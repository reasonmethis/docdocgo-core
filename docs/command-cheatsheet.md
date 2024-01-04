# Command Cheatsheet

You can enter your messages with or without a prefix. Different prefixes activate different response modes.
By default, if a message is entered with no prefix, the `/docs` mode is used.

Here's what each prefix does. Most important prefixes:

- `/research <your query>`: perform Internet research, generate a report, and ingest fetched sites
  - `/research`: fetch more websites and iterate on the previous report
  - `/research for 10 iterations`: repeat the process 10 times
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
- `/research` (to fetch more websites and iterate on the previous report)
- `/research for 10 iterations` (to repeat the process 10 times)
- `/docs Bullet point for me just the ones related to OpenAI`
- `/db` (to manage collections)

If you're in a reading mood, here's a [link to the full docs](https://github.com/reasonmethis/docdocgo-core/blob/main/README.md).

You can also ask DocDocGo for help with using it. By default, it's set up to use the `docdocgo-documentation` collection, which contains its docs. As long as this collection is selected (as shown in the chat box), it should be able to handle most of your questions about how to use it.
