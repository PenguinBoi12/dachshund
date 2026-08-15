# Dachshund

An embedded, real-time hostable admin dashboard for any Python service: FastAPI, Flask,
Django, bots, workers, daemons, etc.

Dachshund runs as a thread inside your process, so there's no router to hook into and
no database to set up. Declare widgets in your code, emit events from anywhere, and
the dashboard updates live over WebSocket.

!!! warning "Under development"
    Dachshund is not usable yet. This documentation grows alongside the implementation.
