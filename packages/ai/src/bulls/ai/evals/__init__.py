"""Eval harness — how we KNOW an AI feature works (not vibes).

Each AI task ships with a labeled eval set + a scorer (exact-match or LLM-as-judge). This is the
core discipline of AI engineering: no AI feature merges without an eval.
"""
