"""Entry point for running as module: python -m transcript_saver_mcp"""
from .server import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
