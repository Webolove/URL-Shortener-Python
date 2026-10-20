"""
app.py — candidate implementation file

Complete the Flask routes for the URL shortener API. The service logic belongs
in shortener.py; the route layer should parse requests, call URLShortener, and
map service outcomes to the required HTTP responses.
"""
from flask import Flask, jsonify, redirect, request

from shortener import (
    CodeGenerationError,
    ConflictError,
    ExpiredLinkError,
    NotFoundError,
    PermissionDeniedError,
    URLShortener,
    ValidationError,
)

app = Flask(__name__)
app.url_map.strict_slashes = False
svc = URLShortener()

def error(message: str, status: int):
    return jsonify({"error": message}), status

def short_url_for(short_code: str) -> str:
    return request.host_url.rstrip("/") + "/" + short_code

@app.get("/data") 
def get_table():
    result = svc.get_table_data()
    for res in result:
        print(res)
    
    return jsonify({"message": "Read server log"}), 200
    

@app.post("/links")
def create_link():
    """
    Create a short link.

    JSON body:
      long_url: required string starting with http:// or https://
      custom_code: optional [A-Za-z0-9_-]{3,32}
      ttl_seconds: optional positive number

    Success: 201 with link metadata, short_url, and owner_token.
    """
    if not request.is_json:
        return error("Content-Type must be application/json", 400)
    
    data = None
    try:
        data = request.get_json()
        
        if not isinstance(data, dict):
            return error("Expected JSON object", 400)
    except Exception as e:
        return error("Malformed JSON", 400)
    
    long_url: str = data.get('long_url')
    custom_code = data.get('custom_code')
    ttl_seconds = data.get('ttl_seconds')
    
    if long_url is not None:
        long_url = "" + long_url
    if custom_code is not None:
        custom_code = "" + custom_code
        
    result = None
    
    try:
        result = svc.create(long_url, custom_code, ttl_seconds)
        
        short_url = short_url_for(result.short_code) 
        return jsonify({**result.to_dict(), "short_url": short_url, "owner_token": result.owner_token}), 201
    except ValidationError as e:
        return error("Input fields are not valid.", 400)
    except ConflictError as e:
        return error("Duplicate custom code are not allowed.", 409)
    except CodeGenerationError as e:
        return error("Unable to generate custom code. Try again later.", 500)
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        return error("Untracked exception.", 500)

    # raise NotImplementedError


@app.get("/<short_code>")
def redirect_link(short_code: str):
    """
    Redirect to the original URL.

    Success: 302 with Location header.
    Missing code: 404.
    Expired code: 410.
    A successful redirect must atomically increment hit_count exactly once.
    """
    try:
        result = svc.resolve_redirect(short_code)
        return redirect(result, code=302)
    except NotFoundError as e:
        return error("Short code not found.", 404)
    except ExpiredLinkError as e:
        return error("Link is expired.", 410)
    # raise NotImplementedError


@app.get("/links/<short_code>")
def get_link(short_code: str):
    """Return metadata for a short link, or 404 when it does not exist."""
    try:
        result = svc.get(short_code)

        if result is None:
            return error("Link does not exist.", 404)
    
        return jsonify({
            "long_url": result.long_url,
            "created_at": result.created_at,
            "expires_at": result.expires_at,
            "hit_count": result.hit_count,
            "is_expired": result.is_expired
        }), 200
        
    except NotFoundError as e:
        return error("Link not found.", 404)
    # raise NotImplementedError


@app.delete("/links/<short_code>")
def delete_link(short_code: str):
    """
    Delete a short link.

    JSON body must contain owner_token.
    Missing token: 400.
    Wrong token: 403.
    Missing code: 404.
    Success: 200 with {"deleted": short_code}.
    """
    data = request.get_json()
    
    owner_token = data.get("owner_token")
    if owner_token is None:
        return error("Missing token", 400)
    
    try:
        svc.delete(short_code, owner_token)
        return jsonify({"deleted": short_code}), 200
    except ValidationError as e:
        return error("Owner token is not valid", 404)
    except PermissionDeniedError as e:
        return error("Owner token not matched", 403)
    except NotFoundError as e:
        return error("Link not found", 404)
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        return jsonify({"message": "Untracked Exception"}), 500
    # raise NotImplementedError


@app.get("/stats")
def stats():
    """Return aggregate statistics across non-deleted links."""
    result = svc.get_stats()
    
    return jsonify(result), 200
    # raise NotImplementedError


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(409)
@app.errorhandler(410)
@app.errorhandler(405)
def handle_http_error(exc):
    return error(getattr(exc, "description", "request failed"), exc.code)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True, threaded=True)
