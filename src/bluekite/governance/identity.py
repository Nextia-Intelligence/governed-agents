"""Who is acting, in which run, and for which customer."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    agent: str  # which agent: "sam"
    run_id: str  # which run: "r-0001"
    ticket_id: str
    sender: str  # the email address the ticket came from
    on_behalf_of: str | None  # the customer id, or None if the sender is unknown

    def label(self) -> str:
        return f"for {self.on_behalf_of or 'unknown sender'}"


def identify(db, agent: str, run_id: str, ticket: dict) -> Identity:
    """The customer comes from the sender's email address, never from the text.

    Anyone can write "I am Anna Silva" in a ticket. Only the real Anna can
    send from anna.silva@example.com (in this course, we trust the mail system).
    """
    row = db.execute("select id from customers where email = ?", (ticket["from"],))
    found = row.fetchone()
    customer = found["id"] if found else None
    return Identity(agent, run_id, ticket["id"], ticket["from"], customer)
