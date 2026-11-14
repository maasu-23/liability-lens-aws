"""draft_documents tool: case facts -> PDF drafts stored in S3, returned as short-lived download links.

The storage call is injected so tests run without AWS. Keys are generated here (drafts/<uuid>/...),
never taken from the caller, and the bucket comes from the Lambda's environment.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from liability_lens import drafts
from liability_lens.pdf import render
from liability_lens.tools import RULES_VERIFIED, ToolInputError

NOTE = ("Drafts only: the user must read them, fill in the bracketed blanks, sign and file them. "
        "Links expire in one hour and the files are deleted within a day.")


def draft_documents(event: dict, store: Callable[[str, bytes], str]) -> dict:
    try:
        docs, blanks, extra = drafts.build(event or {})
    except ToolInputError as e:
        return {"error": str(e)}
    folder = f"drafts/{uuid.uuid4()}"
    out = []
    for doc in docs:
        key = f"{folder}/{doc.kind.replace('_', '-')}.pdf"
        out.append({"kind": doc.kind, "title": doc.title, "key": key, "url": store(key, render(doc))})
    notes = [NOTE]
    if extra["secrets_removed"]:
        notes.append("A code that looked like an OTP, PIN or CVV was removed from the incident summary.")
    return {"documents": out, "fill_in": blanks, "key_dates": extra["key_dates"], "notes": notes,
            "rules_last_verified": RULES_VERIFIED}
