raise SystemExit(
    "The dedicated web_api worker entrypoint was removed. "
    "Start the API with: uvicorn web_api.app:app --host 127.0.0.1 --port 8000"
)
