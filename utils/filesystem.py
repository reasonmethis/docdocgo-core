import os


def ensure_path_exists(path, is_directory=False):
    """
    Ensure that a given path exists as either a file or a directory.

    Parameters:
    - path (str): The file or directory path to check or create.
    - is_directory (bool): Flag to indicate if the path should be a directory (True) or a file (False).

    This function checks if the given path exists. If it exists, it checks if it matches the type specified
    by `is_directory` (file or directory). If it does not exist, the function creates the necessary
    directories and, if required, an empty file at that path.

    Returns:
    - None
    """
    # Check if the path exists
    if os.path.exists(path):
        # If it exists, check if it is the correct type (file or directory)
        if is_directory:
            if not os.path.isdir(path):
                raise ValueError(f"Path {path} exists but is not a directory as expected.")
        elif not os.path.isfile(path):
            raise ValueError(f"Path {path} exists but is not a file as expected.")
    else:
        # If the path does not exist, create it
        if is_directory:
            # Create all intermediate directories
            os.makedirs(path, exist_ok=True)
        else:
            # Create the directory path to the file if it doesn't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # Create the file
            with open(path, "w"):
                pass  # Creating an empty file