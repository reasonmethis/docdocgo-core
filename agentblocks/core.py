from typing import Callable

from utils.strings import extract_json
from utils.type_utils import ChainType, DDGError

MAX_ENFORCE_FORMAT_ATTEMPTS = 4


class EnforceFormatError(DDGError):
    default_user_facing_message = (
        "Apologies, I tried to compose a message in the right "
        "format, but I kept running into trouble."
    )


def enforce_format(
    chain: ChainType,
    inputs: dict,
    validator_transformer: Callable,
    max_attempts: int = MAX_ENFORCE_FORMAT_ATTEMPTS,
):
    """
    Enforce a format on the output of a chain. If the chain fails to produce
    the expected format, retry up to `max_attempts` times. An attempt is considered
    successful if the chain does not raise an exception and the output can be
    transformed using the `validator_transformer`. Return the transformed output. On
    failure, raise an `EnforceFormatError` with a message that includes the last output.
    """
    for i in range(max_attempts):
        output = "OUTPUT_FAILED"
        try:
            output = chain.invoke(inputs)
            return validator_transformer(output)
        except Exception as e:
            err_msg = f"Failed to enforce format. Output:\n\n{output}\n\nError: {e}"
            print(err_msg)
            if i == max_attempts - 1:
                raise EnforceFormatError(err_msg) from e


MAX_ENFORCE_FORMAT_ATTEMPTS = 4


def enforce_json_format(
    chain: ChainType,
    inputs: dict,
    validator_transformer: Callable,  # e.g. pydantic model's validator
    max_attempts: int = MAX_ENFORCE_FORMAT_ATTEMPTS,
):
    return enforce_format(
        chain, inputs, lambda x: validator_transformer(extract_json(x)), max_attempts
    )
