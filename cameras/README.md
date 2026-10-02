Camera source and worker logic are separated from Flask. This keeps frame capture and inference running in background threads rather than inside request handlers.
