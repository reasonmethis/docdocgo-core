from dotenv import load_dotenv

from langchain.schema.language_model import BaseLanguageModel
from langchain.chat_models import ChatOpenAI
from langchain.schema.messages import BaseMessage, HumanMessage, AIMessage
from utils.async_utils import execute_func_map_in_threads

from utils.type_utils import PairwiseChatHistory

load_dotenv()

default_llm_for_token_counting = ChatOpenAI()
def get_num_tokens(text: str, llm_for_token_counting: BaseLanguageModel | None = None):
    """Get the number of tokens in a text."""
    if llm_for_token_counting is None:
        llm_for_token_counting = default_llm_for_token_counting
    return llm_for_token_counting.get_num_tokens(text)


def pairwise_chat_history_to_msg_list(
    chat_history: PairwiseChatHistory,
) -> list[BaseMessage]:
    """Convert a pairwise chat history to a list of messages."""

    msg_list: list[BaseMessage] = []
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


def pairwise_chat_history_to_buffer_string(
    chat_history: PairwiseChatHistory,
    human_prefix="Human",
    ai_prefix="AI",
) -> str:
    """Convert chat history to buffer string such as 'Human: hi\nAI: Hi!\n...'

    See also langchain.schema.messages.get_buffer_string"""

    return "\n".join(
        [
            f"{human_prefix}: {human_msg or '<empty message>'}\n{ai_prefix}: {ai_msg}"
            for human_msg, ai_msg in chat_history
        ]
    )


def limit_chat_history(
    chat_history: PairwiseChatHistory,
    max_token_limit=2000,
    llm_for_token_counting: BaseLanguageModel | None = None,
    cached_token_counts: list[int] | None = None,
) -> tuple[PairwiseChatHistory, list[int]]:
    """Limit the chat history to a maximum number of tokens."""

    if llm_for_token_counting is None and cached_token_counts is None:
        llm_for_token_counting = ChatOpenAI()
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
            token_count_in_pair = llm_for_token_counting.get_num_tokens(
                pairwise_chat_history_to_buffer_string([human_and_ai_msgs])
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
    llm_for_token_counting: BaseLanguageModel,
):
    """Shorten a chat pair to below a maximum number of tokens.

    There is some imprecision in the token counting,
    but it should be ok as long as we only try to shorten long messages."""
    human_msg, ai_msg = human_and_ai_msgs
    if max_token_limit < 10:
        # To prevent infinite loops from inability to shorten
        raise ValueError("max_token_limit must be at least 10")

    # Find the longest message
    human_token_count = llm_for_token_counting.get_num_tokens(human_msg)
    ai_token_count = llm_for_token_counting.get_num_tokens(ai_msg)

    # Shorten the longest message
    tokens_to_remove = curr_token_count - max_token_limit
    if human_token_count > ai_token_count:
        fraction_to_remove = min(0.9, tokens_to_remove / human_token_count)
        human_msg = shorten_msg(human_msg, fraction_to_remove)
    else:
        fraction_to_remove = min(0.9, tokens_to_remove / ai_token_count)
        ai_msg = shorten_msg(ai_msg, fraction_to_remove)

    # Recalculate token count
    token_count_new = llm_for_token_counting.get_num_tokens(
        pairwise_chat_history_to_buffer_string([(human_msg, ai_msg)])
    )

    print(
        f"Shortened pair 'Human: {human_msg[:20]}..., AI: {ai_msg[:20]}...' to "
        f"{token_count_new} tokens. Target was {max_token_limit} tokens."
    )

    # If we are still over the limit, keep shortening
    if token_count_new > max_token_limit:
        return shorten_chat_msg_pair(
            (human_msg, ai_msg),
            max_token_limit,
            token_count_new,
            llm_for_token_counting,
        )

    return (human_msg, ai_msg), token_count_new


def shorten_msg(text: str, fraction_to_remove: float) -> str:
    """Shorten a message to a given fraction of its original length.

    The actual goal is to shorten the token count, but we use words as a proxy,
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
    """
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


def get_num_tokens_in_texts(
    texts: list[str], llm_for_token_counting: BaseLanguageModel | None = None
) -> list[int]:
    """
    Get the number of tokens in a list of texts.
    """

    def _get_num_tokens(text):
        return get_num_tokens(text, llm_for_token_counting)

    token_counts = execute_func_map_in_threads(_get_num_tokens, texts)
    return token_counts


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
