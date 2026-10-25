def register(app):
    from . import account, admin, assistant_routes, auth, catalog, shop
    for m in (catalog, assistant_routes, auth, account, shop, admin):
        app.register_blueprint(m.bp)
