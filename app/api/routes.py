from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/snapshot")
def snapshot(ticker: str = Query(..., description="Ticker symbol, e.g., TSLA")):
    return {"ticker": ticker, "note": "snapshot wiring coming next"}
