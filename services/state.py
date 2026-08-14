import contextvars
import threading
from collections import OrderedDict

# DuckDB connections are not safe for concurrent .execute() calls from
# multiple threads - and unlike a plain DuckDB deployment, cursor() isn't a
# usable escape hatch here: this codebase registers pandas DataFrames as
# tables via conn.register() throughout data_loader.init_data(), and
# register()'d tables are NOT visible from a cursor() derived off the same
# connection (verified directly against the pinned duckdb version - a
# cursor sees only real catalog tables, not registered views). Moving the
# whole data model off register() onto real CREATE TABLE ... AS SELECT
# would be the "proper" fix but is a much larger change than this app's
# scale (small teams, sub-second analytical queries) justifies. A single
# process-wide lock around every DuckDB execute() call serializes query
# execution instead - simple, correct, and the cost is negligible at this
# traffic level. See data_loader.py's query helpers for where this is held.
_duck_query_lock = threading.Lock()

# `_ingestion_pool` keeps a small LRU of recently used ingestions warm (see
# data_loader.get_or_load_ingestion) so switching between a handful of builds
# doesn't pay a full reload every time. It's process-wide on purpose - the
# built LanceDB/DuckDB handles for a given ingestion_id are the same no
# matter which request asks for them.
_ingestion_pool: "OrderedDict[str, dict]" = OrderedDict()

# lance_db/duck_conn/embedder/current_ingestion_id used to be plain module
# globals holding "whichever ingestion is currently active" - but that's a
# single process-wide pointer, and multiple concurrent requests (different
# users looking at different builds at the same time) would stomp on each
# other's copy of it: request A resolves build 1, awaits an LLM call, and by
# the time it resumes and runs its query, request B may have repointed this
# at build 2 - A then reads/queries B's data. ContextVars fix this because
# each incoming request runs in its own asyncio Task, and a Task gets an
# isolated copy of context - reads see whatever THIS request last set, never
# another concurrent request's value. Read via state.duck_conn etc. as
# before (module __getattr__ below); set only through set_active_ingestion/
# set_embedder/clear_active_ingestion, never by plain assignment - a plain
# `state.duck_conn = x` would create a real module attribute that permanently
# shadows the ContextVar for every future reader, silently undoing all of
# this.
#
# Caveat: a ContextVar written inside a thread spawned via
# run_in_threadpool/asyncio.to_thread does NOT propagate back out to the
# async caller (the thread gets its own copy of the context). So
# activation (set_active_ingestion) must happen in the `async def` request
# handler itself, right after awaiting the (threadpool-run) load - never
# inside the synchronous loader function that's the target of that
# threadpool call.
_lance_db_var: "contextvars.ContextVar" = contextvars.ContextVar("lance_db", default=None)
_duck_conn_var: "contextvars.ContextVar" = contextvars.ContextVar("duck_conn", default=None)
_embedder_var: "contextvars.ContextVar" = contextvars.ContextVar("embedder", default=None)
_current_ingestion_id_var: "contextvars.ContextVar" = contextvars.ContextVar("current_ingestion_id", default=None)


def __getattr__(name):
    # PEP 562 module __getattr__: only fires for names not already set as a
    # real module attribute, i.e. exactly the four names below (nothing else
    # in this module shadows them).
    if name == "lance_db":
        return _lance_db_var.get()
    if name == "duck_conn":
        return _duck_conn_var.get()
    if name == "embedder":
        return _embedder_var.get()
    if name == "current_ingestion_id":
        return _current_ingestion_id_var.get()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def set_active_ingestion(ingestion_id, duck_conn, lance_db, embedder) -> None:
    """Point this request's context at a resolved ingestion. Call once, in
    async code, right after `await run_in_threadpool(data_loader.get_or_load_ingestion, ...)`."""
    _current_ingestion_id_var.set(ingestion_id)
    _duck_conn_var.set(duck_conn)
    _lance_db_var.set(lance_db)
    _embedder_var.set(embedder)


def set_embedder(embedder) -> None:
    """Cache a lazily-created embedder for this request's context (see
    data_loader.vector_search)."""
    _embedder_var.set(embedder)


def clear_active_ingestion() -> None:
    _current_ingestion_id_var.set(None)
    _duck_conn_var.set(None)
    _lance_db_var.set(None)
    _embedder_var.set(None)

# RBA: project and role managers (initialized lazily)
project_manager = None
role_manager = None

# LLM usage counters (runtime totals since backend start)
token_usage = {
	"prompt_tokens": 0,
	"completion_tokens": 0,
	"total_tokens": 0,
	"calls": 0,
}
token_usage_by_model = {}