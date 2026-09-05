"""Extension points from system-design.png that are out of scope for the POC.

Each router documents its request contract in OpenAPI and answers 501 so the
architecture is visible in /docs without pretending the pipeline exists.
"""

from fastapi import HTTPException, status


def not_implemented(message: str, planned_flow: list[str]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": message, "planned_flow": planned_flow},
    )
