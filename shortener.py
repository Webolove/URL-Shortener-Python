"""
shortener.py — candidate implementation file

Complete the URLShortener service used by app.py.
You may add helper classes, methods, and constants, but preserve the public
method names used by app.py and the tests.
"""

import re
import sqlite3
import threading
import string   # imported by me
import secrets  # imported by me
import time     # imported by me
import numbers  # imported by me
from urllib.parse import urlparse # imported by me
from dataclasses import dataclass
from typing import Any, Dict, Optional

from db import get_db

AUTO_CODE_PATTERN = re.compile(r"^[A-Za-z0-9]{6,10}$")
CUSTOM_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
MAX_GENERATION_ATTEMPTS = 5


class ShortenerError(Exception):
    pass


class ValidationError(ShortenerError):
    pass


class NotFoundError(ShortenerError):
    pass


class ConflictError(ShortenerError):
    pass


class ExpiredLinkError(ShortenerError):
    pass


class PermissionDeniedError(ShortenerError):
    pass


class CodeGenerationError(ShortenerError):
    pass


@dataclass(frozen=True)
class Link:
    short_code: str
    long_url: str
    created_at: float
    expires_at: Optional[float]
    hit_count: int
    owner_token: str

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < time.time()
        # raise NotImplementedError

    def to_dict(self) -> Dict[str, Any]:
        return {
            "short_code": self.short_code,
            "long_url": self.long_url,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "hit_count": self.hit_count,
            "is_expired": self.is_expired
        }
        # raise NotImplementedError


class URLShortener:
    """
    SQLite-backed short link service.

    Required public methods:
      create(long_url, custom_code=None, ttl_seconds=None) -> Link
      get(short_code) -> Link | None
      resolve_redirect(short_code) -> str
      increment_hits(short_code) -> None
      delete(short_code, owner_token) -> bool
      get_stats() -> dict
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Create the database schema needed by the service."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # schema
       
        cursor.execute("""
                CREATE TABLE IF NOT EXISTS URLTable (
                    long_url TEXT PRIMARY KEY,
                    short_code TEXT UNIQUE NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER DEFAULT -1,
                    hit_count INTEGER DEFAULT 0,
                    owner_token TEXT NOT NULL
            );
        """)
        
        conn.commit()
        # raise NotImplementedError

    def _generate_code(self, long_url: str) -> str:
        """Return a new automatic short code matching [A-Za-z0-9]{6,10}."""
        chars = string.ascii_letters + string.digits
        
        lengths = [6, 7, 8, 9, 10]
        code_len = secrets.choice(lengths)
        
        finalCode =  ''.join(secrets.choice(chars) for _ in range(code_len))
        return finalCode
        # raise NotImplementedError

    def _generate_owner_token(self) -> str:
        """Return a secret token used to authorize deletion."""
        chars = string.ascii_letters + string.digits
        
        lengths = [17, 19, 23, 37, 41]    # Owner token will be of prime lenght. It's my way :)
        code_len = secrets.choice(lengths)
        
        return ''.join(secrets.choice(chars) for _ in range(code_len))
        # raise NotImplementedError

    def is_valid_url(self, url: str) -> bool:
        if url is None or not isinstance(url, str):
            return False

        try:
            parsed = urlparse(url)

            return (
                parsed.scheme in ("http", "https")
                and bool(parsed.hostname)
                and parsed.hostname not in (".", "..")
                and parsed.port != 0
            )
        except ValueError:
            return False

    def create(
        self,
        long_url: str,
        custom_code: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
    ) -> Link:
        """
        Create a short link.

        Raise ValidationError for invalid input.
        Raise ConflictError if a custom code already exists.
        Raise CodeGenerationError if automatic code generation repeatedly collides.
        """
        
        if (custom_code is not None) and (not isinstance(custom_code, str) or (not CUSTOM_CODE_PATTERN.fullmatch(custom_code))):
            raise ValidationError
        
        if ttl_seconds != None and not (isinstance(ttl_seconds, numbers.Number) and not isinstance(ttl_seconds, bool) and ttl_seconds > 0):
            raise ValidationError
            
        if not self.is_valid_url(long_url):
            raise ValidationError
            
        created_at = time.time()
        expires_at = (created_at + ttl_seconds) if ttl_seconds is not None else None
        owner_token = "tok_" + self._generate_owner_token();
        
        final_code = ""
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT short_code FROM URLTable;")
        fetch_codes = cursor.fetchall()
        
        used_codes = []
        for row in fetch_codes:
            used_codes.append(row["short_code"])        
        
        if custom_code != None:
            if custom_code not in used_codes:
                cursor.execute("""
                        REPLACE INTO URLTable (long_url, short_code, created_at, expires_at, hit_count, owner_token) VALUES (?, ?, ?, ?, ?, ?)
                    """, (long_url, custom_code, created_at, expires_at, 0, owner_token,))
                final_code = custom_code
            
            else:
                raise ConflictError
                
        else:            
            code = self._generate_code(long_url)
            created = False
            
            for i in range(MAX_GENERATION_ATTEMPTS):
                if not AUTO_CODE_PATTERN.fullmatch(code):
                    raise CodeGenerationError
                    
                if code not in used_codes:
                    cursor.execute("""
                            REPLACE INTO URLTable (long_url, short_code, created_at, expires_at, hit_count, owner_token) VALUES (?, ?, ?, ?, ?, ?)
                            """, (long_url, code, created_at, expires_at, 0, owner_token,))
                    created = True
                            
                    final_code = code
                    break
                else:
                    code = self._generate_code(long_url)
                            
            if not created:
                raise CodeGenerationError                    
            
        conn.commit()
        # conn.close()
            
        return Link(final_code, long_url, created_at, expires_at, 0, owner_token)   
    
    def get_table_data(self):
        conn = get_db();
        cursor = conn.cursor();
        
        cursor.execute("SELECT * FROM URLTable;")
        rows = cursor.fetchall()
        
        ans = []
        for row in rows:
            ans.append([row["long_url"], row["owner_token"], row["short_code"], row["expires_at"]])
        return ans
        
    def get(self, short_code: str) -> Optional[Link]:
        """Return the link for short_code, or None when it does not exist."""        
        conn = self._get_conn();
        cursor = conn.cursor();
        
        result = None
        
        try:
            cursor.execute("SELECT * FROM URLTable WHERE short_code = ?", (short_code,))
            result = cursor.fetchone()
        except Exception as e:
            return None
        
        if result is None:
            return None
        
        return Link(short_code, result["long_url"], result["created_at"], result["expires_at"], result["hit_count"], result["owner_token"])
        # raise NotImplementedError

    def resolve_redirect(self, short_code: str) -> str:
        """
        Return the long URL for a redirect and atomically count the hit.

        Raise NotFoundError if the code does not exist.
        Raise ExpiredLinkError if the link is expired.
        """
        with self._lock:
            currTime = time.time()
                        
            conn = self._get_conn();
            cursor = conn.cursor();
                        
            result = None
            
            try:    
                cursor.execute("SELECT * FROM URLTable WHERE short_code = ?", (short_code,))
                result = cursor.fetchone()
            except Exception as e:
                raise NotFoundError
                        
            if result is None:
                raise NotFoundError
                        
            expires_at = result["expires_at"]
            # print(expires_at, " ", currTime)
            if expires_at is not None and expires_at <= currTime:
                # Delete expired URL if required
                # cursor.execute("DELETE FROM URLTable WHERE long_url = ?", (result["long_url"],))  # Lazy deletion of expired URL
                # conn.commit()
                raise ExpiredLinkError                    
        
        self.increment_hits(short_code)
        return result["long_url"]
        # raise NotImplementedError

    def increment_hits(self, short_code: str) -> None:
        """
        Atomically increment hit_count for an existing short code.

        Raise NotFoundError if the code does not exist.
        """

        with self._lock:
            conn = self._get_conn()
            cursor = conn.cursor()
                
            # cursor.execute("BEGIN TRANSACTION")
            cursor.execute("UPDATE URLTable SET hit_count = hit_count + 1 WHERE short_code = ?", (short_code,))
            # rows = cursor.fetchall()

            if cursor.rowcount == 0:
                raise NotFoundError
            # cursor.execute("COMMIT")
                        
            conn.commit()
            
        # raise NotImplementedError

    def delete(self, short_code: str, owner_token: str) -> bool:
        """
        Delete a link if owner_token matches.

        Return True when deleted, False when the code does not exist.
        Raise ValidationError when owner_token is missing or empty.
        Raise PermissionDeniedError when the token is wrong.
        """
        if owner_token == "":
            raise ValidationError
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        result = None
        
        cursor.execute("SELECT * FROM URLTable WHERE short_code = ?", (short_code,))
        if cursor.rowcount == 0:
            return False
                
        result = cursor.fetchone()
        if result is None:
            return False
        
        actual_owner_token = "" + result["owner_token"]
            
        if actual_owner_token != owner_token:
            raise PermissionDeniedError
            
        cursor.execute("DELETE FROM URLTable WHERE short_code = ?", (short_code,))
        conn.commit()
        return True
        # raise NotImplementedError

    def get_stats(self) -> Dict[str, Any]:
        """Return total_links, total_hits, and the top five links by hit count."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM URLTable;")
        rows = cursor.fetchall()
        all_URL = []
        
        total_links = 0
        total_hits = 0
        for row in rows:
            total_links += 1
            total_hits += row["hit_count"]
            all_URL.append([row["hit_count"], row["short_code"], row["long_url"]])
            
        all_URL.sort(key=lambda x: (-x[0], x[1]))
        
        top_5_links = []
        len = total_links if total_links <= 5 else 5
        
        for i in range(len):
            top_5_links.append({
                "short_code": all_URL[i][1],
                "long_url": all_URL[i][2],
                "hit_count": all_URL[i][0]
            })
        
        ans = Dict[str, Any]
        ans = {
            "total_links": total_links,
            "total_hits": total_hits,
            "top_5_links": top_5_links
        }
        
        return ans
        # raise NotImplementedError

    def _get_conn(self) -> sqlite3.Connection:
        return get_db(self._db_path)