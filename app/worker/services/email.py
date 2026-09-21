from uuid import uuid7
from sqlalchemy.orm import Session


from app.api.schemas.email import EmailInDB
from app.api.repo.email import EmailRepository
from app.api.services.email import EmailService


class TaskEmail:
    def __init__(self, session: Session):
        self._session = session
        self._email_service = EmailService(
            email_repo=EmailRepository(sync_session=self._session)
        )

    def create_email(
        self, email_subject: str, email_message: str, recipient_email: str
    ) -> dict:
        email_id = uuid7()

        email_db: EmailInDB = EmailInDB(id=email_id, processed_email=recipient_email)
        self._email_service.create_email_sync(email_db)

        payload = {
            "email_subject": email_subject,
            "email_message": email_message,
            "email_id": str(email_id),
            "recipient_email": recipient_email,
        }
        return payload
