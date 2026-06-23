"""Common interface for all solvers."""
from abc import ABC, abstractmethod

from scheduling.models.job import ProblemInstance
from scheduling.models.schedule import Schedule


class BaseSolver(ABC):
    """Common interface shared by every solver."""

    @abstractmethod
    def solve(self, instance: ProblemInstance) -> Schedule:
        """Solve the scheduling problem and return a Schedule with KPIs."""
        ...

    def get_name(self) -> str:
        return self.__class__.__name__
