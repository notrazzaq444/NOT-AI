from urllib.parse import urlparse

def validate_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("A valid HTTP(S) URL is required.")
    return url

def clean_user_text(value: str, max_length: int = 12000) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Text cannot be empty.")
    if len(value) > max_length:
        raise ValueError(f"Text exceeds {max_length} characters.")
    return value
