"""Background execution support for the Tkinter application."""

from threading import Event, Thread

from . import agent


def start_run(api_key, doc_path, view_path, out_dir, on_log, on_done):
    """Start an agent run in a daemon thread and return its cancellation handle."""
    cancel_event = Event()

    def work():
        try:
            result = agent.run_agent(
                api_key,
                doc_path,
                view_path,
                out_dir,
                log=on_log,
                cancel_event=cancel_event,
            )
        except Exception as error:
            message = str(error) or error.__class__.__name__
            on_done({"error": message})
        else:
            on_done(result)

    thread = Thread(target=work, daemon=True)
    thread.start()
    return thread, cancel_event
