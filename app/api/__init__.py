def register_api_blueprints(app):
    from app.api.assistant import assistant_api_bp
    from app.api.bonds import bonds_api_bp
    from app.api.equities import equities_api_bp
    from app.api.exchange_rates import exchange_rates_api_bp
    from app.api.indices import indices_api_bp
    from app.api.insights import insights_api_bp
    from app.api.market import market_api_bp
    from app.api.order_book import order_book_api_bp
    from app.api.reports import reports_api_bp

    app.register_blueprint(reports_api_bp, url_prefix="/api/reports")
    app.register_blueprint(equities_api_bp, url_prefix="/api/equities")
    app.register_blueprint(bonds_api_bp, url_prefix="/api/bonds")
    app.register_blueprint(indices_api_bp, url_prefix="/api/indices")
    app.register_blueprint(exchange_rates_api_bp, url_prefix="/api/exchange-rates")
    app.register_blueprint(market_api_bp, url_prefix="/api/market")
    app.register_blueprint(order_book_api_bp, url_prefix="/api/order-book")
    app.register_blueprint(insights_api_bp, url_prefix="/api/insights")
    app.register_blueprint(assistant_api_bp, url_prefix="/api/assistant")
