### GPT-4o mini and other updates

First, DocDocGo had a teeny-tiny issue with its database growing too gigantic for its VM. The issue is now fixed, so if you tried to use DocDocGo and couldn't access it, my apologies - it's now back in action! :muscle::

Updates:

**For users:** 

1. The default model is now **Gemini 2.5 Flash**, so expect a significant improvement in the quality of responses. If you use DocDocGo with you own OpenRouter API key, you can also switch to any model available on OpenRouter.
2. The database has been upgraded and cleaned up for better performance.

**For developers:** 

1. The [developer docs](https://github.com/reasonmethis/docdocgo-core/blob/main/README-FOR-DEVELOPERS.md) have been significantly expanded to include lots of goodies on hosting the Chroma database server on AWS and GCP, running locally with Docker, cleaning it, etc. There is a lot more that can (and should) be added, so if something is unclear or you have any questions or suggestions, feel free to DM me here or on [LinkdIn](https://www.linkedin.com/in/dmitriyvasilyuk/).
2. In addition to cleaning up the database, Langchain and Chroma DB have been upgraded to the latest versions (0.2.10 and 0.5.4, respectively). A slew of deprecated imports have been updated, and a bug related to a breaking change in Langchain's `Chroma` has been found and squashed :beetle:.

I hope you enjoy using DocDocGo with the shiny new GPT-4o mini! Because of the model switch and other major changes, it's possible that there may be some hiccups that I haven't caught yet. Feel free to reach out on [GitHub](https://github.com/reasonmethis/docdocgo-core) if you see any :spider:, and the exterminator will be dispatched posthaste!

## Formatted for LinkedIn

### DocDocGo updates: GPT-4o mini and other news ###

- App: https://docdocgo.streamlit.app
- GitHub: https://github.com/reasonmethis/docdocgo-core

🚀 The default model is now GPT-4o mini instead of GPT-3.5, so expect a significant improvement in the quality of responses. If you use DocDocGo with you own OpenAI API key, you can also switch to GPT-4o, GPT-4, or the old friend GPT-3.5.

⚡ The database has been upgraded and cleaned up for better performance.

📝 The developer docs (https://github.com/reasonmethis/docdocgo-core/blob/main/README-FOR-DEVELOPERS.md) have been significantly expanded to include lots of goodies on hosting the Chroma database server on AWS and GCP, running locally with Docker, cleaning it, etc. There is a lot more that can (and should) be added, so if you have any questions or suggestions, feel free to DM me.

🔧 In addition to cleaning up the database, Langchain and Chroma DB have been upgraded to the latest versions (0.2.10 and 0.5.4, respectively). A slew of deprecated imports have been updated, and a bug related to a breaking change in Langchain's `Chroma` has been found and squashed 🪲.

📢 If this is your first time hearing about DocDocGo, it's an AI assistant that helps you find information that requires sifting through far more than the first page of Google search results. It's kind of like if ChatGPT, Perplexity and GPT Researcher had a 👶

I hope you enjoy using DocDocGo with the shiny new GPT-4o mini! Because of the model switch and other major changes, it's possible that there may be some hiccups that I haven't caught yet. Feel free to reach out here or on GitHub (https://github.com/reasonmethis/docdocgo-core) if you see any 🕷️, and the exterminator will be dispatched posthaste!