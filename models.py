from pydantic import BaseModel

class StripeEvent(BaseModel):
    type: str
