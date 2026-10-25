"""Start-up account provisioning and (clearly flagged) demo seeding. Passwords are never logged and never have defaults."""
import datetime as dt
import logging
import random

from sqlalchemy import func, select

from . import config, security, store
from .models import Order, OrderEvent, OrderItem, Product, User, utcnow
from .services import cart as cart_svc

log = logging.getLogger("bootstrap")
DEMO_USERS = [("Demo Shopper", "demo.shopper@verity.example"), ("Asha Rao (demo)", "demo.asha@verity.example"),
              ("Kabir Mehta (demo)", "demo.kabir@verity.example"), ("Neha Iyer (demo)", "demo.neha@verity.example")]


def ensure_admin(db, email: str, password: str, name: str = "Store Admin", demo: bool = False) -> str:
    email = security.normalise_email(email)
    if not security.valid_email(email):
        raise ValueError("Admin email is not a valid address.")
    problem = security.password_problem(password, email, name)
    if problem:
        raise ValueError("Admin password rejected: " + problem)
    with db.scope() as s:
        u = s.scalar(select(User).where(User.email == email))
        if u:
            if u.role != "admin":
                u.role = "admin"
            return "existing"
        s.add(User(email=email, name=name, password_hash=security.hash_password(password), role="admin", is_demo=demo, password_changed_at=utcnow()))
    return "created"


def seed_demo(db, password: str, orders: int = 36, seed: int = 42, settings: dict | None = None) -> dict:
    """Creates 4 demo customers and `orders` historical orders flagged is_demo=True. Idempotent. Stock is not touched."""
    problem = security.password_problem(password)
    if problem:
        raise ValueError("Demo password rejected: " + problem)
    rnd = random.Random(seed)
    settings = settings or config.load_settings()
    with db.scope() as s:
        if s.scalar(select(func.count()).select_from(Order).where(Order.is_demo.is_(True))):
            return {"users": 0, "orders": 0, "skipped": "demo data already present"}
        users = []
        for name, email in DEMO_USERS:
            u = s.scalar(select(User).where(User.email == email))
            if not u:
                u = User(email=email, name=name, password_hash=security.hash_password(password), is_demo=True, password_changed_at=utcnow())
                s.add(u)
            users.append(u)
        s.flush()
        prods = s.scalars(select(Product).where(Product.is_active.is_(True), Product.price_paise.is_not(None))).unique().all()
        cities = [("Vijayawada", "Andhra Pradesh", "520010"), ("Hyderabad", "Telangana", "500081"), ("Bengaluru", "Karnataka", "560001"), ("Chennai", "Tamil Nadu", "600017")]
        now = utcnow()
        made = 0
        for n in range(orders):
            u = users[0] if n < 7 else rnd.choice(users)
            days = rnd.randint(0, 29) if n >= 7 else rnd.randint(1, 28)
            created = now - dt.timedelta(days=days, hours=rnd.randint(0, 20))
            lines, subtotal = [], 0
            for p in rnd.sample(prods, rnd.randint(1, 3)):
                v = rnd.choice(store.active_variants(p)) if store.active_variants(p) else None
                qty = rnd.choice([1, 1, 1, 2])
                unit = store.unit_price_paise(p, v)
                subtotal += unit * qty
                lines.append(OrderItem(product_id=p.id, variant_id=v.id if v else None, sku=v.sku if v else p.sku, title=p.title, brand=p.brand,
                                       category=p.category.name if p.category else "", variant_label=store.variant_label(v), image=(p.images or [""])[0],
                                       unit_price_paise=unit, quantity=qty, line_total_paise=unit * qty))
            ship = cart_svc.shipping_for(subtotal, settings)
            status = "cancelled" if rnd.random() < .08 else "delivered" if days > 9 else "shipped" if days > 5 else "processing" if days > 2 else "placed"
            city, state, pin = rnd.choice(cities)
            o = Order(order_number=f"VO-DEMO{n:04d}", user_id=u.id, status=status, payment_method="demo_card", payment_status="demo_simulated", subtotal_paise=subtotal,
                      shipping_paise=ship, total_paise=subtotal + ship, contact_email=u.email, ship_name=u.name, ship_phone="9876543210", ship_line1="12 Demo Street",
                      ship_city=city, ship_state=state, ship_pincode=pin, is_demo=True, created_at=created, updated_at=created)
            o.items = lines
            chain = ["placed", "processing", "shipped", "delivered"]
            steps = chain[:chain.index(status) + 1] if status != "cancelled" else ["placed", "cancelled"]
            o.events = [OrderEvent(status=st, note="Seeded demo order", actor="system", at=created + dt.timedelta(hours=8 * i)) for i, st in enumerate(steps)]
            s.add(o)
            made += 1
    return {"users": len(DEMO_USERS), "orders": made}


def run(app):
    cfg, db = app.config, app.extensions["verity"].db
    if cfg["ADMIN_EMAIL"] and cfg["ADMIN_PASSWORD"]:
        try:
            log.info("Admin bootstrap for %s: %s", cfg["ADMIN_EMAIL"], ensure_admin(db, cfg["ADMIN_EMAIL"], cfg["ADMIN_PASSWORD"]))
        except ValueError as e:
            log.error("ADMIN_EMAIL/ADMIN_PASSWORD ignored: %s", e)
    if cfg["SEED_DEMO"]:
        with db.scope() as s:
            source = store.meta_get(s, "catalogue_source")
        if source not in store.SYNTHETIC_SOURCES:
            log.error("SEED_DEMO ignored: the catalogue is not synthetic (%s).", source)
        elif not cfg["DEMO_PASSWORD"]:
            log.error("SEED_DEMO needs DEMO_PASSWORD (there is no default).")
        else:
            try:
                log.info("Demo seed: %s", seed_demo(db, cfg["DEMO_PASSWORD"], settings=dict(cfg)))
            except ValueError as e:
                log.error("SEED_DEMO ignored: %s", e)
