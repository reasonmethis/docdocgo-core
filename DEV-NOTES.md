# Dev Notes

## get_relevant_documents on a retriever

- calls _get_relevant_documents
- for vectorstores, that calls self.vectorstore.similarity_search_with_relevance_scores(query, **self.search_kwargs)
- _similarity_search_with_relevance_scores
- similarity_search_with_score
- for chroma, that calls self.__query_collection(query_embeddings=[query_embedding], n_results=k, where=filter)
  - besides k and filter, no other search_kwargs are passed (specifically where_document),
    even though it accepts arbitrary kwargs
- self._collection.query(
            query_texts=query_texts,
            query_embeddings=query_embeddings,
            n_results=n_results,
            where=where,
            **kwargs,
        )

## Assorted TODOs

1. DONE chromadb.api.models.Collection has feature to filter by included text and metadatas (I think)
2. Eval mode: gives two answers, user likes one, bot tunes params
3. Generate several versions of the standalone query
4. Use tasks in case answer takes too long (meanwhile can show a tip)
5. Ability for user to customize bot settings (num of docs, relevance threshold, temperature, etc.)
6. Make use of larger context window
7. Reorder relevant documents in order (based on overlap e.g.)
8. DONE API token for the bot backend
9. For long convos include short summary in the prompt
10. DONE Use streaming to improve detecting true LLM stalls
11. Send partial results to the user to avoid timeout
12. Return retrieved documents in the response
13. Speed up limiting tokens - see tiktoken comment in OpenAIEmbeddings
14. Add ability to (auto)update vector db
15. DONE Include current date/time in the prompt
16. Use two different chunk sizes: search for small chunks, then small chunks point to larger chunks

## Evaluations

### Research tasks

1. "extract main content from html"

## Discovered Tricks for Getting Content from Websites

1. To help with bot detection, it helps to set a different device in playwright
    - e.g. "iphone13"
    - For example, this helped with the following links:
        - "https://www.sciencedaily.com/news/computers_math/artificial_intelligence/",
        - "https://www.investors.com/news/technology/ai-stocks-artificial-intelligence-trends-and-news/",
        - "https://www.forbes.com/sites/forbesbusinesscouncil/2022/10/07/recent-advancements-in-artificial-intelligence/?sh=266cd08e7fa5",
2. I increased the MIN_EXTRACTED_SIZE setting from 250 to 1500 in trafilatura to extract more content
    - for example, in the following link, with the default setting it only extracted a cookie banner:
        - "https://www.artificialintelligence-news.com/"
