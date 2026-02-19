# Contributing to Fulloch

Thank you for your interest in contributing to Fulloch! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up the development environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   # Install special packages (see requirements.txt for details)
   pip install --no-deps git+https://github.com/rekuenkdr/Qwen3-TTS-streaming.git
   # GPU only: pip install --no-build-isolation --no-deps git+https://github.com/Dao-AILab/flash-attention.git@ef9e6a6
   pip install -e ".[dev]"  # Install dev dependencies
   ```
4. Copy environment template:
   ```bash
   cp .env.example .env
   ```
5. Edit `.env` with your settings

## Adding New Tools

Fulloch uses a decorator-based tool registry system. To add a new tool:

### Step 1: Create a new tool file

Create `tools/my_tool.py`:

```python
\"\"\"My new tool description.\"\"\"
import os

from .tool_registry import tool, tool_registry

# Load env configuration if needed
MY_SETTING = os.getenv(\"MY_SETTING\", \"default\")


@tool(
    name="my_function",
    description="What this function does (shown to AI)",
    aliases=["alias1", "alias2"]  # Optional alternative names
)
def my_function(param1: str, param2: int = 10) -> str:
    """
    Detailed docstring for the function.

    Args:
        param1: Description of param1
        param2: Description of param2 (default: 10)

    Returns:
        Result message
    """
    # Implementation here
    return f"Result: {param1}, {param2}"
```

### Step 2: Register the tool

Add the import to `tools/__init__.py`:

```python
from . import my_tool
```

Add to the `__all__` list:

```python
__all__ = [
    # ... existing tools ...
    'my_tool',
]
```

### Step 3: Add environment variables (if needed)

Add variables to `.env.example`:

```bash
MY_SETTING=default_value
MY_OTHER_SETTING=123
```

### Step 4: Test your tool

```bash
python tools/my_tool.py
```

## Code Style Guidelines

- Follow PEP 8 style guidelines
- Use type hints for function parameters and return values
- Write docstrings for all public functions and classes
- Keep functions focused and single-purpose
- Use meaningful variable and function names

### Logging

Use the standard logging module:

```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

### Async Functions

For I/O-bound operations (network, file system), use async:

```python
import asyncio

async def _my_async_function():
    """Internal async implementation."""
    # async code here
    pass


@tool(name="my_function", description="...")
def my_function():
    """Sync wrapper for the async function."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_my_async_function())
    else:
        return loop.create_task(_my_async_function())
```

## Pull Request Process

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/my-feature
   ```

2. Make your changes and commit with clear messages:
   ```bash
   git commit -m "Add my new feature"
   ```

3. Run tests before submitting:
   ```bash
   pytest tests/
   ```

4. Push to your fork and create a Pull Request

5. Fill out the PR template with:
   - Summary of changes
   - Test plan
   - Any breaking changes

## Reporting Issues

When reporting issues, please include:

- Python version (`python --version`)
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant log output

## Questions?

Feel free to open an issue for questions or discussion about potential contributions.
