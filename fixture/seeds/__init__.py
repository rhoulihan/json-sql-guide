"""Seed profiles for the fixture loader.

Each profile module exposes a ``load(conn)`` callable that inserts rows
for its theme. Profiles are composable — callers request one or more
via ``FixtureLoader(profiles=[...])``.
"""
