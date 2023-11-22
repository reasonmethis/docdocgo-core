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
13. Add support for Jira
14. Add ability to (auto)update vector db
15. Include current date/time in the prompt
16. Use two different chunk sizes: search for small chunks, then small chunks point to larger chunks
