from enum import Enum


class BaseStatus(str, Enum):
    FAILED = "failed"
    PENDING = "pending"


class TransactionStatus(BaseStatus):
    SUCCESS = "success"
    REJECTED = "rejected"
    ABANDONED = "abandoned"


class RefundStatus(BaseStatus):
    PROCESSED = "processed"
    PROCESSING = "processing"
    NEEDS_ATTENTION = "needs_attention"
