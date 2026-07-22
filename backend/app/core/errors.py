"""Application-specific exceptions."""


class SessionNotFoundError(Exception):
    """The chat_session_id cookie references a session that does not exist.

    Raised only by the session-verification step of the chat pipelines and caught by the
    chat routes to return the 404 session_not_found response. Deliberately NOT a
    ValueError: the routes previously caught bare ValueError, which mislabeled unrelated
    pipeline failures (e.g. fd-exhaustion connection errors) as an expired session.
    """
