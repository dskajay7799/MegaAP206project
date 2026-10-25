"""SQLAlchemy models. Money is stored as integer paise; timestamps are UTC. Portable across SQLite (dev) and PostgreSQL (prod)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class UTCDateTime(TypeDecorator):
    """Always stores and returns timezone-aware UTC, even on SQLite which drops tzinfo."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return (value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value.astimezone(dt.timezone.utc))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value.astimezone(dt.timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dt.datetime: UTCDateTime, dict: JSON, list: JSON}


class Meta(Base):
    __tablename__ = "meta"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="customer")          # customer | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime, nullable=True)
    password_changed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AuthSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(UTCDateTime)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(UTCDateTime)
    used_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str] = mapped_column(String(80), default="")
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    subcategory: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    price_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mrp_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)       # NULL = not tracked, use stock_status
    stock_status: Mapped[str] = mapped_column(String(16), default="unknown")
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    specs: Mapped[dict] = mapped_column(JSON, default=dict)                      # typed values, see specs.py
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)                 # free-form string attributes (imported data)
    highlights: Mapped[list] = mapped_column(JSON, default=list)
    use_cases: Mapped[list] = mapped_column(JSON, default=list)
    images: Mapped[list] = mapped_column(JSON, default=list)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    data_origin: Mapped[str] = mapped_column(String(16), default="catalogue")    # demo | catalogue | admin
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    updated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    category: Mapped[Category | None] = relationship(lazy="joined")
    variants: Mapped[list["Variant"]] = relationship(back_populates="product", cascade="all, delete-orphan", order_by="Variant.id", lazy="selectin")


class Variant(Base):
    __tablename__ = "product_variants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(80), unique=True)
    options: Mapped[dict] = mapped_column(JSON, default=dict)                    # {"size": "M", "colour": "Navy"}
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    price_delta_paise: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    product: Mapped[Product] = relationship(back_populates="variants")


class PriceObservation(Base):
    __tablename__ = "price_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    price_paise: Mapped[int] = mapped_column(Integer)
    observed_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String(24), default="catalogue")         # catalogue | admin | simulated-demo


class Cart(Base):
    __tablename__ = "carts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=True)
    guest_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    items: Mapped[list["CartItem"]] = relationship(back_populates="cart", cascade="all, delete-orphan", order_by="CartItem.id", lazy="selectin")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "product_id", "variant_key", name="uq_cart_line"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=True)
    variant_key: Mapped[str] = mapped_column(String(16), default="")             # '' or str(variant_id): makes the unique constraint work with NULLs
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    added_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)
    cart: Mapped[Cart] = relationship(back_populates="items")


class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_wishlist"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)


class RecentView(Base):
    __tablename__ = "recent_views"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_recent"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    viewed_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)


class Address(Base):
    __tablename__ = "addresses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(40), default="Home")
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    line1: Mapped[str] = mapped_column(String(200))
    line2: Mapped[str] = mapped_column(String(200), default="")
    city: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(80))
    pincode: Mapped[str] = mapped_column(String(6))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_order_idem"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="placed", index=True)
    payment_method: Mapped[str] = mapped_column(String(24), default="demo")
    payment_status: Mapped[str] = mapped_column(String(24), default="demo_simulated")
    subtotal_paise: Mapped[int] = mapped_column(Integer)
    shipping_paise: Mapped[int] = mapped_column(Integer, default=0)
    total_paise: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    contact_email: Mapped[str] = mapped_column(String(254), default="")
    ship_name: Mapped[str] = mapped_column(String(120), default="")
    ship_phone: Mapped[str] = mapped_column(String(20), default="")
    ship_line1: Mapped[str] = mapped_column(String(200), default="")
    ship_line2: Mapped[str] = mapped_column(String(200), default="")
    ship_city: Mapped[str] = mapped_column(String(80), default="")
    ship_state: Mapped[str] = mapped_column(String(80), default="")
    ship_pincode: Mapped[str] = mapped_column(String(6), default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    updated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id", lazy="selectin")
    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order", cascade="all, delete-orphan", order_by="OrderEvent.id", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True)
    sku: Mapped[str] = mapped_column(String(80), default="")
    title: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str] = mapped_column(String(80), default="")
    category: Mapped[str] = mapped_column(String(80), default="")
    variant_label: Mapped[str] = mapped_column(String(120), default="")
    image: Mapped[str] = mapped_column(String(500), default="")
    unit_price_paise: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    line_total_paise: Mapped[int] = mapped_column(Integer)
    order: Mapped[Order] = relationship(back_populates="items")


class OrderEvent(Base):
    __tablename__ = "order_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(String(200), default="")
    actor: Mapped[str] = mapped_column(String(16), default="system")             # system | customer | admin
    at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)
    order: Mapped[Order] = relationship(back_populates="events")


class SavedComparison(Base):
    __tablename__ = "saved_comparisons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    product_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)


class Preference(Base):
    __tablename__ = "preferences"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    budget_min_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    budget_max_paise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requirements: Mapped[list] = mapped_column(JSON, default=list)               # catalogue use-case tags / feature keys
    updated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class SavedChat(Base):
    __tablename__ = "saved_chats"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)


class PriceWatch(Base):
    __tablename__ = "price_watches"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_watch"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    target_price_paise: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow)


class ChatLog(Base):
    __tablename__ = "chat_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    session_id: Mapped[str] = mapped_column(String(40), default="")
    message: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="")
    mode: Mapped[str] = mapped_column(String(16), default="")
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[dt.datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    session_id: Mapped[str] = mapped_column(String(40), default="")
    request_id: Mapped[str] = mapped_column(String(16), default="")
    helpful: Mapped[bool] = mapped_column(Boolean)


Index("ix_orders_user_created", Order.user_id, Order.created_at)
