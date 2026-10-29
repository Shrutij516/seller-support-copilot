"""Retrieval-augmented answers for seller chat: retrieve policy chunks, keep only the
relevant ones, and have the model answer strictly from them with numbered citations.

`types` holds the interfaces route handlers depend on; `prompt` is pure (no I/O) and owns
everything the model sees; `bedrock` is the only module that talks to AWS.
"""
