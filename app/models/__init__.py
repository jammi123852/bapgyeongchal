"""모델 패키지.

alembic autogenerate 와 metadata 등록을 위해 모든 모델을 여기서 import 한다.
"""

from app.models.inventory_item import InventoryItem
from app.models.inventory_item_event import InventoryItemEvent
from app.models.product import Product
from app.models.recommendation import Recommendation
from app.models.user import User
from app.models.user_action import UserAction

__all__ = [
    "InventoryItem",
    "InventoryItemEvent",
    "Product",
    "Recommendation",
    "User",
    "UserAction",
]
