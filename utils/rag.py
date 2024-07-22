from langchain_text_splitters import RecursiveCharacterTextSplitter

rag_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=400,
    chunk_overlap=40,
    add_start_index=True,  # metadata will include start index of snippet in original doc
)
