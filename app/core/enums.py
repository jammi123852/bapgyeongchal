"""도메인 enum 정의.

중요 원칙 (docs/mvp-v0_1-freeze.md 기준):

- InventoryStatus 는 **식품의 상태**다.
- UserActionType 은 그 상태를 바꾸게 만든 **사용자의 행동**이다.
- 두 개념을 하나의 enum 으로 합치지 않는다.
  예) EXPIRED(상태) vs MARKED_EXPIRED(행동)
"""

from enum import Enum


class InventoryStatus(str, Enum):
    """InventoryItem 의 현재 상태."""

    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    DISCARDED = "DISCARDED"
    EXPIRED = "EXPIRED"


class StorageType(str, Enum):
    """보관 위치."""

    FRIDGE = "FRIDGE"
    FREEZER = "FREEZER"
    PANTRY = "PANTRY"


class UserActionType(str, Enum):
    """사용자가 기록한 one-tap action.

    MARKED_EXPIRED 는 '기한이 지난 것으로 표시했다'는 행동이며,
    그 결과로 InventoryStatus.EXPIRED 가 된다.
    """

    CONSUMED = "CONSUMED"
    PARTIALLY_CONSUMED = "PARTIALLY_CONSUMED"
    DISCARDED = "DISCARDED"
    MARKED_EXPIRED = "MARKED_EXPIRED"


class Actor(str, Enum):
    """행동/이벤트의 주체.

    SYSTEM 은 아직 생성되지 않지만(배치 없음), 나중에 자동 판정을 도입할 때
    사용자 기록과 섞이면 학습 라벨이 오염되므로 처음부터 컬럼을 분리해 둔다.
    """

    USER = "USER"
    SYSTEM = "SYSTEM"


class ExpirySource(str, Enum):
    """소비기한 값의 출처. OCR 값도 사용자가 확인한 뒤에만 저장된다.

    OCR 정확도와 사용자 수정률을 나중에 측정하기 위해 구분해 둔다.
    """

    MANUAL = "MANUAL"
    OCR = "OCR"


class InventoryEventType(str, Enum):
    """InventoryItem 변경 이력 유형."""

    CREATED = "CREATED"
    EXPIRY_CHANGED = "EXPIRY_CHANGED"
    OPENED_DATE_CHANGED = "OPENED_DATE_CHANGED"
    STORAGE_CHANGED = "STORAGE_CHANGED"
    QUANTITY_CHANGED = "QUANTITY_CHANGED"
    STATUS_CHANGED = "STATUS_CHANGED"
    DELETED = "DELETED"
    RESTORED = "RESTORED"


class ProductSource(str, Enum):
    """Product 정보의 출처.

    Step 1 에서는 외부 API 를 호출하지 않는다. 값 정의만 둔다.
    """

    MANUAL = "MANUAL"
    C005 = "C005"
    I2570 = "I2570"
    HACCP = "HACCP"
    OFF = "OFF"
