
from utils.prepare import get_logger
from langchain_core.prompts import PromptTemplate

logger = get_logger()


def save_prompt_text_to_file(
    prompt: PromptTemplate, inputs: dict[str, str], file_path: str
) -> None:
    prompt_text = prompt.invoke(inputs).to_string()
    with open(file_path, "a", encoding="utf-8") as f:
        f.write("-" * 80 + "\n\n" + prompt_text)
    logger.debug(f"Saved prompt text to {file_path}")
