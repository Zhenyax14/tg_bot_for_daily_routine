from __future__ import annotations

from domain.value_objects.instrument import Instrument

INSTRUMENTS: list[Instrument] = [
    # Acciones "Magníficas" (US, Yahoo Finance)
    Instrument("AAPL", "Apple", "us", "us_stock", "$"),
    Instrument("MSFT", "Microsoft", "us", "us_stock", "$"),
    Instrument("GOOGL", "Alphabet", "us", "us_stock", "$"),
    Instrument("AMZN", "Amazon", "us", "us_stock", "$"),
    Instrument("NVDA", "Nvidia", "us", "us_stock", "$"),
    Instrument("META", "Meta", "us", "us_stock", "$"),
    Instrument("TSLA", "Tesla", "us", "us_stock", "$"),
    Instrument("AVGO", "Broadcom", "us", "us_stock", "$"),
    # Fondos mayoritarios (ETF índices US, Yahoo Finance)
    Instrument("SPY", "S&P 500 (SPY)", "us", "us_etf", "$"),
    Instrument("QQQ", "Nasdaq 100 (QQQ)", "us", "us_etf", "$"),
    Instrument("DIA", "Dow Jones (DIA)", "us", "us_etf", "$"),
    Instrument("IWM", "Russell 2000 (IWM)", "us", "us_etf", "$"),
    Instrument("URTH", "MSCI World (URTH)", "us", "us_etf", "$"),
    # Criptomonedas (Yahoo Finance, mismo endpoint que las acciones US)
    Instrument("BTC-USD", "Bitcoin", "crypto", "crypto", "$"),
    Instrument("ETH-USD", "Ethereum", "crypto", "crypto", "$"),
    # Acciones MOEX (RU, blue chips del índice IMOEX)
    Instrument("SBER", "Сбербанк", "ru", "ru_stock", "₽"),
    Instrument("GAZP", "Газпром", "ru", "ru_stock", "₽"),
    Instrument("LKOH", "Лукойл", "ru", "ru_stock", "₽"),
    Instrument("YDEX", "Яндекс", "ru", "ru_stock", "₽"),
    Instrument("GMKN", "Норникель", "ru", "ru_stock", "₽"),
    Instrument("ROSN", "Роснефть", "ru", "ru_stock", "₽"),
    Instrument("NVTK", "Новатэк", "ru", "ru_stock", "₽"),
    Instrument("TATN", "Татнефть", "ru", "ru_stock", "₽"),
    Instrument("MTSS", "МТС", "ru", "ru_stock", "₽"),
    Instrument("MGNT", "Магнит", "ru", "ru_stock", "₽"),
    Instrument("PLZL", "Полюс", "ru", "ru_stock", "₽"),
    Instrument("CHMF", "Северсталь", "ru", "ru_stock", "₽"),
    # Divisas (MOEX CETS, pares contra RUB con negociación activa; cotizan en
    # rublos por unidad, de ahí la moneda "₽")
    Instrument("USD000UTSTOM", "Доллар США / ₽", "fx", "fx", "₽"),
    Instrument("CNYRUB_TOM", "Юань / ₽", "fx", "fx", "₽"),
    Instrument("TRYRUB_TOM", "Турецкая лира / ₽", "fx", "fx", "₽"),
    Instrument("KZTRUB_TOM", "Тенге / ₽", "fx", "fx", "₽"),
]
