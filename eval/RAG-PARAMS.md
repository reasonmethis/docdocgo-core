# Parameters for RAG

## ChromaDDGRetriever

    k_min = 2  # min number of docs to return after pruning
    score_threshold_min = 0.61  # use k_min if score of k_min'th doc is <= this
    k_max = 10  # max number of docs to return after pruning
    score_threshold_max = 0.76  # use k_max if score of k_max'th doc is >= this

## prepare_chunks

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=40, 
