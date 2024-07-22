from bisect import bisect_right
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from utils.algo import insert_interval
from utils.async_utils import execute_func_map_in_threads
from utils.output import ConditionalLogger
from utils.prepare import get_logger
from utils.rag import rag_text_splitter
from utils.type_utils import PairwiseChatHistory
from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, get_buffer_string

logger = get_logger()

default_llm_for_token_counting = ChatOpenAI(api_key="DUMMY")  # "DUMMY" to avoid error

## https://gptforwork.com/guides/openai-gpt3-tokens
# English: 1 word ≈ 1.3 tokens
# French: 1 word ≈ 2 tokens
# German: 1 word ≈ 2.1 tokens
# Spanish: 1 word ≈ 2.1 tokens
# Chinese: 1 word ≈ 2.5 tokens
# Russian: 1 word ≈ 3.3 tokens
# Vietnamese: 1 word ≈ 3.3 tokens
# Arabic: 1 word ≈ 4 tokens
# Hindi: 1 word ≈ 6.4 tokens

ROUGH_UPPER_LIMIT_AVG_CHARS_PER_TOKEN = 4  # English: 1 word ≈ 1.3 tokens


def get_token_ids(text: str, llm_for_token_counting: BaseLanguageModel | None = None):
    """Get the token IDs for a text."""
    llm = llm_for_token_counting or default_llm_for_token_counting
    # return llm.get_token_ids(text) # can result in:
    # ValueError: Encountered text corresponding to disallowed special token '<|endoftext|>'
    _, tiktoken_encoding = llm._get_encoding_model()
    return tiktoken_encoding.encode_ordinary(text)  # LC uses encode instead


def get_num_tokens(text: str, llm_for_token_counting: BaseLanguageModel | None = None):
    """Get the number of tokens in a text."""
    return len(get_token_ids(text, llm_for_token_counting))


def get_num_tokens_in_texts(
    texts: list[str], llm_for_token_counting: BaseLanguageModel | None = None
) -> list[int]:
    """
    Get the number of tokens in a list of texts using multiple threads.
    """

    def _get_num_tokens(text):
        return get_num_tokens(text, llm_for_token_counting)

    # TODO: experiment - since this is CPU-bound, may not benefit from threads
    token_counts = execute_func_map_in_threads(_get_num_tokens, texts)
    return token_counts


def pairwise_chat_history_to_msg_list(
    chat_history: PairwiseChatHistory,
) -> list[BaseMessage]:
    """Convert a pairwise chat history to a list of messages."""

    msg_list = []
    for human_msg, ai_msg in chat_history:
        msg_list.append(HumanMessage(content=human_msg))
        msg_list.append(AIMessage(content=ai_msg))
    return msg_list


def msg_list_chat_history_to_pairwise(
    msg_list: list[BaseMessage],
) -> PairwiseChatHistory:
    """Convert a list of messages to a pairwise chat history."""
    raise NotImplementedError("Not yet fully implemented and tested.")
    chat_history: PairwiseChatHistory = []
    for i in range(0, len(msg_list), 2):
        chat_history.append((msg_list[i].content, msg_list[i + 1].content))
    return chat_history


def pairwise_chat_history_to_string(
    chat_history: PairwiseChatHistory,
    human_prefix="Human",
    ai_prefix="AI",
) -> str:
    """Convert chat history to a string such as 'Human: hi\nAI: Hi!\n...'

    See also langchain.schema.messages.get_buffer_string"""

    return "\n".join(
        [
            f"{human_prefix}: {human_msg or '<empty message>'}\n{ai_prefix}: {ai_msg}"
            for human_msg, ai_msg in chat_history
        ]
    )


def msg_list_chat_history_to_string(
    msg_list: list[BaseMessage],
    human_prefix="Human",
    ai_prefix="AI",
) -> str:
    """
    Convert a list of messages to a string such as 'Human: hi\nAI: Hi!\n...'
    """
    return get_buffer_string(msg_list, human_prefix, ai_prefix)


def limit_chat_history(
    chat_history: PairwiseChatHistory,
    max_token_limit=2000,
    llm_for_token_counting: BaseLanguageModel | None = None,
    cached_token_counts: list[int] | None = None,
) -> tuple[PairwiseChatHistory, list[int]]:
    """
    Limit the chat history to a maximum number of tokens.
    """

    # msgs = pairwise_chat_history_to_msg_list(chat_history)
    # token_counts = [
    #     llm_for_token_counting.get_num_tokens_from_messages([m]) for m in msgs
    # ]

    # The above would be one way, but we can do it without converting to messages
    if cached_token_counts and len(cached_token_counts) != len(chat_history):
        raise ValueError(
            f"Incorrect cached_token_counts length {len(cached_token_counts)}"
            f". Expected {len(chat_history)}"
        )

    tot_token_count = 0
    token_counts_from_end = []
    shortened_msgs, tokens_in_shortened_msgs = [], []

    for i, human_and_ai_msgs in enumerate(reversed(chat_history)):
        if cached_token_counts:
            token_count_in_pair = cached_token_counts[-i - 1]
        else:
            token_count_in_pair = get_num_tokens(
                pairwise_chat_history_to_string([human_and_ai_msgs]),
                llm_for_token_counting,
            )

        tot_token_count += token_count_in_pair

        if tot_token_count > max_token_limit:
            num_pairs = i
            # If current pair is quite long, shorten it and also include it
            num_tokens_can_add = max_token_limit - (
                tot_token_count - token_count_in_pair
            )
            if llm_for_token_counting and num_tokens_can_add > max_token_limit / 3:
                (
                    human_and_ai_msgs_shortened,
                    token_count_shortened,
                ) = shorten_chat_msg_pair(
                    human_and_ai_msgs,
                    num_tokens_can_add,
                    token_count_in_pair,
                    llm_for_token_counting,
                )
                # Create list with one shortened pair to prepend to chat history
                shortened_msgs = [human_and_ai_msgs_shortened]
                tokens_in_shortened_msgs = [token_count_shortened]

            break
        token_counts_from_end.append(token_count_in_pair)

    else:  # no break
        num_pairs = len(chat_history)

    return (
        (shortened_msgs + chat_history[-num_pairs:]) if num_pairs else shortened_msgs,
        tokens_in_shortened_msgs + token_counts_from_end[::-1],
    )


def shorten_chat_msg_pair(
    human_and_ai_msgs,
    max_token_limit,
    curr_token_count,
    llm_for_token_counting: BaseLanguageModel | None = None,
):
    """
    Shorten a chat pair to below a maximum number of tokens.

    There is some imprecision in the token counting,
    but it should be ok as long as we only try to shorten long messages.
    """
    human_msg, ai_msg = human_and_ai_msgs
    if max_token_limit < 10:
        # To prevent infinite loops from inability to shorten
        raise ValueError("max_token_limit must be at least 10")

    # Find the longest message
    human_token_count = get_num_tokens(human_msg, llm_for_token_counting)
    ai_token_count = get_num_tokens(ai_msg, llm_for_token_counting)

    # Shorten the longest message
    tokens_to_remove = curr_token_count - max_token_limit
    if human_token_count > ai_token_count:
        fraction_to_remove = min(0.9, tokens_to_remove / human_token_count)
        human_msg = shorten_text_remove_middle(human_msg, fraction_to_remove)
    else:
        fraction_to_remove = min(0.9, tokens_to_remove / ai_token_count)
        ai_msg = shorten_text_remove_middle(ai_msg, fraction_to_remove)

    # Recalculate token count
    token_count_new = get_num_tokens(
        pairwise_chat_history_to_string([(human_msg, ai_msg)]),
        llm_for_token_counting,
    )

    # print(
    #     f"Shortened pair 'Human: {human_msg[:20]}..., AI: {ai_msg[:20]}...' to "
    #     f"{token_count_new} tokens. Target was {max_token_limit} tokens."
    # )

    # If we are still over the limit, keep shortening
    if token_count_new > max_token_limit:
        return shorten_chat_msg_pair(
            (human_msg, ai_msg),
            max_token_limit,
            token_count_new,
            llm_for_token_counting,
        )

    return (human_msg, ai_msg), token_count_new


def shorten_text_remove_middle(text: str, fraction_to_remove: float) -> str:
    """
    Shorten a text to a given fraction of its original length by removing the middle
    and replacing it with " ... ".

    Usually the intended measure of the length is tokens but we use words as a proxy,
    by splitting on spaces.
    """
    words = text.split(" ")  # NOTE could use RecursiveCharacterTextSplitter
    num_words_to_keep = int(len(words) * (1 - fraction_to_remove))
    if num_words_to_keep < 4:
        return "..."
    return (
        " ".join(words[: num_words_to_keep // 2 - 1])
        + " ... "
        + " ".join(words[-(num_words_to_keep // 2 - 1) :])
    )


def limit_tokens_in_text(
    text: str,
    max_tokens: int,
    llm_for_token_counting: BaseLanguageModel | None = None,
    slow_down_factor=1.0,  # 0 = quicker but can undershoot significantly
) -> str:
    """
    Limit the number of tokens in a text to the specified amount (or slightly less).

    Tokens are removed from the end of the text.
    """

    # NOTE: Can implement without "guesses", using get_token_ids and token lookup
    words = text.split(" ")
    num_tokens = 0
    at_most_words = len(words)

    # Get the initial guess for the number of words to keep
    # print("max_tokens:", max_tokens)
    # print("Initial token counting...")
    for i, word in enumerate(words):
        curr_num_tokens = get_num_tokens(word, llm_for_token_counting)
        num_tokens += curr_num_tokens
        if num_tokens > max_tokens:
            at_most_words = i
            break
    # print("actual number of words:", len(words))
    # print("at_most_words:", at_most_words)

    # Keep reducing the number of words to keep until we're below the token limit
    while True:
        text = " ".join(words[:at_most_words])
        true_num_tokens = get_num_tokens(text, llm_for_token_counting)
        if true_num_tokens <= max_tokens:
            return text, true_num_tokens
        # Reduce the number of words to keep and try again
        # print("true_num_tokens:", true_num_tokens)
        # print("at_most_words:", at_most_words, end=" -> ")
        at_most_words = int(
            at_most_words
            * (max_tokens / true_num_tokens + slow_down_factor)
            / (1 + slow_down_factor)
        )
        # print(at_most_words)


def get_max_token_allowance_for_texts(
    texts: list[str], max_tot_tokens: int, cached_token_counts: list[int] | None = None
) -> tuple[int, list[int]]:
    """
    Get the number of tokens we must limit each text to in order to keep the total
    number of tokens below the specified amount.

    Returns that number (the "allowance") and a list of token counts for each text.
    """
    token_counts = (
        get_num_tokens_in_texts(texts)
        if cached_token_counts is None
        else cached_token_counts
    )
    is_allowance_redistributed_list = [False] * len(texts)
    allowance = max_tot_tokens // (len(texts) or 1)
    while True:
        # Calculate "unused allowance" we can "give" to other texts
        unused_allowance = 0
        num_texts_with_excess = 0
        for i, (num_tokens, is_already_redistributed) in enumerate(
            zip(token_counts, is_allowance_redistributed_list)
        ):
            if is_already_redistributed:
                continue
            if num_tokens > allowance:
                num_texts_with_excess += 1
            else:
                unused_allowance += allowance - num_tokens
                # Mark as already redistributed (will redistribute by increasing allowance)
                is_allowance_redistributed_list[i] = True

        # If no allowance to give, we're done
        if (
            num_texts_with_excess == 0
            or (allowance_increment := unused_allowance // num_texts_with_excess) == 0
        ):
            break

        # Distribute unused allowance and recalculate
        # print("num_texts_with_excess:", num_texts_with_excess)
        # print("allowance", allowance, end=" -> ")
        allowance += allowance_increment
        # print(allowance)

    return allowance, token_counts


def limit_tokens_in_texts(
    texts: list[str],
    max_tot_tokens: int,
    cached_token_counts: list[int] | None = None,
) -> tuple[list[str], list[int]]:
    """
    Limit the number of tokens in a list of texts to the specified amount (or slightly less).

    Returns a list of updated texts and a list of token counts for each text.
    """
    allowance, token_counts = get_max_token_allowance_for_texts(
        texts, max_tot_tokens, cached_token_counts
    )
    # print("max_tot_tokens:", max_tot_tokens)
    # print("numbert of texts:", len(texts))
    # print("allowance:", allowance)
    new_texts = []
    new_token_counts = []
    for text, num_tokens in zip(texts, token_counts):
        if num_tokens > allowance:
            text, num_tokens = limit_tokens_in_text(text, max_tokens=allowance)
        new_texts.append(text)
        new_token_counts.append(num_tokens)
    return new_texts, new_token_counts


def expand_chunks(
    base_chunks: list[Document],
    parents_by_id: dict[str, Document],
    max_total_tokens: int,
    boost_factor_top: float = 1.4,  # boost token allowance for top chunk, decrease linearly
    ratio_add_above_vs_below: float = 0.5,  # approx. ratio of tokens to add above vs below
    llm_for_token_counting: BaseLanguageModel | None = None,
    keep_chunk_order: bool = True,
) -> list[Document]:
    """
    Expand chunks using their parent documents. The expanded chunks will have a total
    number of tokens below the specified limit (or slightly above). The expanded chunks
    will have the same metadata as the base chunks, except for the "start_index" metadata,
    which will be updated to reflect the new start index in the parent document, and the
    "num_tokens" metadata, which will contain the chunk's number of tokens.

    If during expansion two or more chunks in the same parent document overlap, they will
    be merged into one chunk.

    If keep_chunk_order is True, the order of the final chunks will be determined by the earliest
    base chunk within each final chunk. If False, all final chunks belonging to the same parent
    document will go one after the other in the order they appear in the parent document, and the
    order of the parent documents will be determined by the earliest base chunk within each parent
    document.
    """

    clg = ConditionalLogger(verbose=False)  # NOTE: can use an environment variable

    num_base_chunks = len(base_chunks)
    if num_base_chunks == 0:
        return []

    # Split each parent document into chunks
    parent_chunks_by_id: dict[str, list[Document]] = {
        id_: rag_text_splitter.split_documents([doc])
        for id_, doc in parents_by_id.items()
    }

    # Determine the location of each chunk in its parent document chunks
    chunk_idxs = []
    for base_chunk in base_chunks:
        parent_id = base_chunk.metadata["parent_id"]
        start_index = base_chunk.metadata["start_index"]
        parent_chunks = parent_chunks_by_id[parent_id]

        # Find the index of the parent chunk identical to chunk
        for i, parent_chunk in enumerate(parent_chunks):
            if parent_chunk.metadata["start_index"] == start_index:
                chunk_idxs.append(i)
                break
        else:
            raise ValueError(f"Parent for start_index {start_index} not found.")

    # Determine target expasion boost factor for each base chunk - vs avg expanded size
    if num_base_chunks == 1:
        boost_factors = [1.0]
    else:
        # Linearly decrease boost factor from e.g. 1.4 to 0.6
        boost_factor_step = 2 * (boost_factor_top - 1) / (num_base_chunks - 1)
        boost_factors = [
            boost_factor_top - boost_factor_step * i for i in range(num_base_chunks)
        ]

    # Prepare to keep track of the expanded chunks
    final_chunks_by_id: dict[str, dict[tuple[int, int], Document]] = {}

    token_allowance_left = max_total_tokens
    num_base_chunks_left = num_base_chunks
    boost_factors_sum_left = num_base_chunks

    # Expand each base chunk and merge overlapping chunks
    for base_chunk, boost_factor, chunk_idx in zip(
        base_chunks, boost_factors, chunk_idxs
    ):
        parent_id = base_chunk.metadata["parent_id"]
        parent_doc_text = parents_by_id[parent_id].page_content
        parent_chunks = parent_chunks_by_id[parent_id]
        num_parent_chunks = len(parent_chunks)

        # Variables to keep track of the expanded chunk
        start_idx = base_chunk.metadata["start_index"]
        end_idx = start_idx + len(base_chunk.page_content)
        start_chunk_idx = chunk_idx
        end_chunk_idx = chunk_idx + 1

        # Expanded chunk starts with the original chunk
        num_tokens = get_num_tokens(base_chunk.page_content, llm_for_token_counting)
        expanded_chunk = Document(
            page_content=base_chunk.page_content,
            metadata=base_chunk.metadata | {"num_tokens": num_tokens},
        )

        target_num_tokens = token_allowance_left * boost_factor / boost_factors_sum_left
        clg.log(
            f"{num_tokens = }, {token_allowance_left = }, "
            f"{target_num_tokens = }, {boost_factor = }"
        )

        # Keep expanding the chunk until it reaches the target size
        # If, e.g. ratio_add_above_vs_below = 0.5, we want to add 2 chunks below for
        # every chunk above (below, above, below, below, above, below, ...)
        added_above = added_below = 0
        while True:
            # Determine whether to add above or below
            if start_chunk_idx == 0:
                if end_chunk_idx == num_parent_chunks:
                    break  # no more chunks to add
                add_above = False
            elif end_chunk_idx == num_parent_chunks:
                add_above = True
            else:
                score_if_add_above = (
                    added_above + 1 - added_below * ratio_add_above_vs_below
                )
                score_if_add_below = (
                    added_above - (added_below + 1) * ratio_add_above_vs_below
                )
                add_above = abs(score_if_add_above) <= abs(score_if_add_below) + 1e-6

            # Get the chunk to add and update number of tokens in the expanded chunk
            new_chunk_idx = start_chunk_idx - 1 if add_above else end_chunk_idx
            chunk_to_add = parent_chunks[new_chunk_idx]
            chunk_to_add_start_idx = chunk_to_add.metadata["start_index"]
            new_start_idx = chunk_to_add_start_idx if add_above else start_idx
            new_end_idx = (
                end_idx
                if add_above
                else chunk_to_add_start_idx + len(chunk_to_add.page_content)
            )

            new_text = parent_doc_text[new_start_idx:new_end_idx]
            new_num_tokens = get_num_tokens(new_text, llm_for_token_counting)

            # If adding this chunk would exceed the target size, stop
            # NOTE: we are always including the original chunk, even if it
            # exceeds the target size on its own. That's why the total number
            # of tokens in the final expanded chunks can be slightly above the target.
            if new_num_tokens > target_num_tokens:
                break

            # Add the base chunk by updating the relevant variables
            if add_above:
                start_idx = new_start_idx
                start_chunk_idx -= 1
                added_above += 1
            else:
                end_idx = new_end_idx
                end_chunk_idx += 1
                added_below += 1

            # Update the expanded chunk
            expanded_chunk = Document(
                page_content=new_text,
                metadata=base_chunk.metadata
                | {"num_tokens": new_num_tokens, "start_index": new_start_idx},
            )
        clg.log(
            f"New num_tokens: {expanded_chunk.metadata['num_tokens']}, "
            f"{start_idx = }, {end_idx = }, "
            f"{added_above = }, {added_below = }"
        )

        # We have determined the expanded chunk. Update chunk info for parent document
        curr_chunks_in_parent = final_chunks_by_id.get(parent_id, {})
        curr_chunk_boundaries = list(curr_chunks_in_parent.keys())
        new_chunk_boundaries = insert_interval(
            curr_chunk_boundaries, (start_idx, end_idx)
        )  # some chunks may have been merged
        new_chunks_in_parent: dict[tuple[int, int], Document] = {}
        for idx_pair in new_chunk_boundaries:
            try:
                # If we already have this expanded chunk, keep it
                new_chunks_in_parent[idx_pair] = curr_chunks_in_parent[idx_pair]
            except KeyError:
                # We don't have info for this expanded chunk yet, so add it
                if idx_pair == (start_idx, end_idx):
                    # The unaltered expanded chunk we just constructed
                    new_chunks_in_parent[idx_pair] = expanded_chunk
                else:
                    # Some sort of merged chunk. Construct it and add it
                    chunk_text = parent_doc_text[idx_pair[0] : idx_pair[1]]
                    num_tokens = get_num_tokens(chunk_text, llm_for_token_counting)
                    new_chunks_in_parent[idx_pair] = Document(
                        page_content=chunk_text,
                        metadata=base_chunk.metadata
                        | {
                            "start_index": idx_pair[0],
                            "num_tokens": num_tokens,
                        },
                    )
        final_chunks_by_id[parent_id] = new_chunks_in_parent

        # Update remaining token allowance (only tokens used from parent doc changed)
        orig_num_tokens_in_parent = sum(
            x.metadata["num_tokens"] for x in curr_chunks_in_parent.values()
        )
        new_num_tokens_in_parent = sum(
            x.metadata["num_tokens"] for x in new_chunks_in_parent.values()
        )
        token_allowance_left -= new_num_tokens_in_parent - orig_num_tokens_in_parent

        clg.log(f"{token_allowance_left = }")
        clg.log("=-" * 20)

        # Update accounting variables for the next base chunk to expand
        num_base_chunks_left -= 1
        boost_factors_sum_left -= boost_factor

    # We have expanded all base chunks. Return the expanded chunks
    final_chunks = []
    if keep_chunk_order:
        # Prepare idx_pairs_by_parent_id for each parent_id
        idx_pairs_by_parent_id = {
            parent_id: list(final_chunks_in_parent.keys())
            for parent_id, final_chunks_in_parent in final_chunks_by_id.items()
        }
        used_idx_pairs_by_parent_id = {
            parent_id: set() for parent_id in final_chunks_by_id
        }

        # Find and add the final chunks in the order of the base chunks
        for base_chunk in base_chunks:
            parent_id = base_chunk.metadata["parent_id"]
            idx_pairs = idx_pairs_by_parent_id[parent_id]
            # Use bisect_right to find which final chunk contains the base chunk
            idx_pair = idx_pairs[
                bisect_right(
                    idx_pairs,
                    base_chunk.metadata["start_index"],
                    key=lambda x: x[0],  # use start index for comparisons
                )
                - 1
            ]
            # Add the final chunk if it hasn't been added yet
            if idx_pair not in used_idx_pairs_by_parent_id[parent_id]:
                final_chunks.append(final_chunks_by_id[parent_id][idx_pair])
                used_idx_pairs_by_parent_id[parent_id].add(idx_pair)

    else:
        for parent_id in final_chunks_by_id:
            final_chunks.extend(final_chunks_by_id[parent_id].values())

    return final_chunks
