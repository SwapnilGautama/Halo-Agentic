import datetime

def log_event(event_type, payload):
    timestamp = datetime.datetime.utcnow().isoformat()
    log = {
        "timestamp": timestamp,
        "event_type": event_type,
        "payload": payload
    }

    with open("app_logs.jsonl", "a") as f:
        f.write(str(log) + "\n")
