"""Credential lookup that survives a stale process environment.

The problem this solves is Windows-specific and catches everyone once. Environment
variables are inherited from the parent process at launch, not read live. So after
``setx NEUPRINT_APPLICATION_CREDENTIALS ...`` writes the value to the registry, every
process that was ALREADY running -- VS Code, its terminals, anything they spawn -- keeps
the old environment, which does not contain it. Opening a new terminal does not help,
because its parent is the same stale VS Code. Even "Developer: Reload Window" does not
help, because that restarts the renderer, not the main process.

The result is a token that is correctly stored and simultaneously invisible, producing a
bare 401 that looks like a bad token rather than a stale shell.

So: check the process environment first, then fall back to reading the registry directly.
The registry is the authoritative store on Windows; the environment is just a cached copy.
"""

from __future__ import annotations

import os
import sys

NEUPRINT_ENV_VAR = "NEUPRINT_APPLICATION_CREDENTIALS"


def _read_windows_user_env(name: str) -> str | None:
    """Read a user environment variable straight from the registry (Windows only)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return None

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value).strip() or None
    except (FileNotFoundError, OSError):
        return None


def get_token(env_var: str = NEUPRINT_ENV_VAR, required: bool = True) -> str | None:
    """Resolve an API token, tolerating a stale inherited environment.

    Args:
        env_var: environment variable holding the token.
        required: raise a diagnostic error when absent rather than returning None.
    """
    token = (os.environ.get(env_var) or "").strip()
    if token:
        return token

    from_registry = _read_windows_user_env(env_var)
    if from_registry:
        # Cache it for the rest of this process, and for anything it spawns.
        os.environ[env_var] = from_registry
        print(
            f"  note: {env_var} was missing from this process's environment but present "
            "in the registry. Using the stored value.\n"
            "        (This shell was started before the variable was set. Fully quitting "
            "and reopening VS Code makes it inherit normally.)"
        )
        return from_registry

    if not required:
        return None

    raise RuntimeError(_missing_token_message(env_var))


def _missing_token_message(env_var: str) -> str:
    """Explain which of the two failure modes actually happened."""
    in_registry = _read_windows_user_env(env_var) is not None
    if in_registry:
        return (
            f"{env_var} is stored but could not be read. The value exists in the "
            "registry, so this is a permissions or encoding problem rather than a "
            "missing token."
        )
    return (
        f"No {env_var} found.\n"
        "\n"
        "  Get a token:  https://neuprint.janelia.org  ->  Account  ->  Auth Token\n"
        "  Store it:     setx " + env_var + " \"<token>\"\n"
        "\n"
        "  Note that setx truncates values over 1024 characters; use the GUI dialog\n"
        "  (search 'Edit environment variables for your account') for longer tokens.\n"
        "\n"
        "  It takes effect in THIS session immediately with:\n"
        "      $env:" + env_var + " = "
        "[Environment]::GetEnvironmentVariable('" + env_var + "','User')\n"
        "\n"
        "  Never put the token in a file inside this repo."
    )
