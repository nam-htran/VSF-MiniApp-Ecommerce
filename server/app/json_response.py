"""JSON that cannot be mistaken for markup.

Sellers write product names and descriptions, so every response carries
text this server did not author. `Content-Type: application/json` already
stops a browser executing it, and a React client escapes on render — but
neither is true of every consumer, and a body containing a literal
`<script>` is one careless `innerHTML` away from being a stored XSS.

So the three characters that start a tag or an entity are emitted as their
\\u escapes. The value is unchanged — `json.loads` gives back exactly what
the seller typed — but the bytes on the wire can no longer be read as HTML.
Cheap, and it removes a whole class of client mistake.
"""

import json
from typing import Any

from fastapi.responses import JSONResponse

_ESCAPES = {
    ord("<"): "\\u003c",
    ord(">"): "\\u003e",
    ord("&"): "\\u0026",
}


class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        text = json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        return text.translate(_ESCAPES).encode("utf-8")
