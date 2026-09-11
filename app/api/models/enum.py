from enum import Enum


class TransactionStatus(str, Enum):
    FAILED = "failed"
    PENDING = "pending"
    SUCCESS = "success"
    REJECTED = "rejected"
    ABANDONED = "abandoned"


class RefundStatus(str, Enum):
    FAILED = "failed"
    PENDING = "pending"
    PROCESSED = "processed"
    PROCESSING = "processing"
    NEEDS_ATTENTION = "needs_attention"


class EmailStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class OtpStatus(str, Enum):
    VALID = "valid"
    USED = "used"


class OutBoxEnum(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    PROCESSING = "processing"


class SourceEnum(str, Enum):
    WEBHOOK = "webhook"
    USER_ACTION = "user_action"
    RECONCILIATION = "reconciliation"


class ChannelEnum(str, Enum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"


class UserType(str, Enum):
    EMAIL = "email"
    GOOGLE = "google"


class CurrencyEnum(str, Enum):
    NGN = "NGN"
