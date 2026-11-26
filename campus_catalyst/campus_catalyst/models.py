from dataclasses import dataclass, asdict
from datetime import date
import uuid

VALID_STATUSES = {"Pending", "Approved", "Rejected"}


@dataclass
class VolunteerRecord:
    volunteer_name: str
    activity: str
    category: str
    service_date: str
    start_time: str
    end_time: str
    hours: float
    status: str = "Pending"
    supervisor: str = ""
    notes: str = ""
    deadline: str = ""
    record_id: str = ""

    def __post_init__(self):
        if not self.record_id:
            self.record_id = self.new_id()

    @staticmethod
    def new_id():
        return uuid.uuid4().hex[:8].upper()

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})

    @property
    def fingerprint(self):
        """Identity of a session, used to skip duplicates when importing."""
        return (self.volunteer_name.casefold(), self.activity.casefold(),
                self.service_date, self.start_time, self.end_time)

    @property
    def is_overdue(self):
        if not self.deadline or self.status != "Pending":
            return False
        try:
            return date.fromisoformat(self.deadline) < date.today()
        except ValueError:
            return False
