from typing import Any, Iterable

def get_menu_choice(
    choices: Iterable[str],
    prompt: str = "Please enter the desired number: ",
    default: int | None = None,
) -> int:
    """
    Get a choice from the user from a list of choices.

    Returns the index of the choice selected by the user. Prompts the user
    repeatedly until a valid choice is entered.
    """

    while True:
        # Print the choices with numbered identifiers
        for idx, choice_text in enumerate(choices, start=1):
            print(f"{idx}. {choice_text}")

        # Prompt for the user's choice
        user_input = input(prompt)

        # Use default if the user input is empty and default is set
        if user_input == "" and default is not None:
            return default

        # Check if the input is a valid choice
        try:
            chosen_idx = int(user_input) - 1
        except ValueError:
            chosen_idx = -1
        if 0 <= chosen_idx < len(choices):
            return chosen_idx 
        print()

def get_choice_from_dict_menu(
    menu: dict[Any, str],
    prompt: str = "Please enter the desired number: ",
    default: Any | None = None,
) -> Any:
    """
    Get a choice from the user from a dictionary menu.

    Returns the key of the choice selected by the user. Prompts the user
    repeatedly until a valid choice is entered.
    """

    default_idx = None if default is None else -123
    idx = get_menu_choice(menu.values(), prompt, default_idx)
    return default if idx == -123 else list(menu.keys())[idx]
     