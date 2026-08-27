"""Launch bot.py with the keyword-reaction listener installed globally.

This keeps reaction handling independent of the bot's media-download on_message
handler, so reactions work in every channel without changing the bot's existing
message-processing flow.
"""

import asyncio
import runpy

import discord

from keyword_reactions import react_to_message


_original_dispatch = discord.Client.dispatch


def _dispatch_with_reactions(self, event, /, *args, **kwargs):
    result = _original_dispatch(self, event, *args, **kwargs)

    if event == "message" and args:
        message = args[0]
        try:
            asyncio.create_task(react_to_message(message))
        except RuntimeError:
            # No running event loop. Discord will handle the normal dispatch;
            # this only protects startup/shutdown edge cases.
            pass

    return result


discord.Client.dispatch = _dispatch_with_reactions

if __name__ == "__main__":
    runpy.run_path("bot.py", run_name="__main__")
