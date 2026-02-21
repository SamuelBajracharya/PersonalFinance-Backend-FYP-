from sqlalchemy.orm import Session

from app.models.stock_instrument import StockInstrument


def get_stock_instruments_by_user(db: Session, user_id: str) -> list[StockInstrument]:
    return (
        db.query(StockInstrument)
        .filter(StockInstrument.user_id == user_id)
        .order_by(StockInstrument.symbol.asc())
        .all()
    )


def get_stock_instrument_by_user_and_symbol(
    db: Session, user_id: str, symbol: str
) -> StockInstrument | None:
    return (
        db.query(StockInstrument)
        .filter(
            StockInstrument.user_id == user_id,
            StockInstrument.symbol == symbol.upper(),
        )
        .first()
    )
