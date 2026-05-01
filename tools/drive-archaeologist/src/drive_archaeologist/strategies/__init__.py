from abc import ABC, abstractmethod


class Strategy(ABC):
    @abstractmethod
    def match(self, path: str) -> bool:
        pass

    @abstractmethod
    def extract(self, path: str) -> dict | None:
        pass
