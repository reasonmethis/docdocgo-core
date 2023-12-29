"""Load the environment variables and perform other initialization tasks."""
from utils.prepare import is_env_loaded

if not is_env_loaded:
    raise RuntimeError("This should be unreachable.")
