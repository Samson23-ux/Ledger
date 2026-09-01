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
