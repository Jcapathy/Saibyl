"""Housekeeping that runs beside the product rather than inside a request.

One module today: `reaper`, which closes jobs the process died in the middle
of. It exists because every worker here writes a non-terminal status, does its
work, and writes a terminal one — and a deploy between those two writes leaves
a founder watching a spinner forever.
"""
