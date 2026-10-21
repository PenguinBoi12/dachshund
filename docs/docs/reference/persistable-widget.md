# Persistable Widget

`PersistableWidget` is the base for a widget type that can keep its own state across a restart. Subclassing it is a promise to implement `accumulate`, `snapshot`, and `restore`; a subclass missing one can't be built.

Persisting stays optional per widget: `persist` defaults to `False`, and without it the hooks are never called. With `persist=True`, the dashboard needs a `Storage` configured, see the [Persistent Storage](../guides/persistent-storage.md) guide. Building a type that doesn't subclass `PersistableWidget` with `persist=True` raises `TypeError`.

For state that's one entry per string key, subclass [KeyedWidget](keyed-widget.md) instead.

::: dachshund.widgets.persistable.PersistableWidget
