"""Minimal entity registry. Entity = int ID; components stored in typed dicts."""
from __future__ import annotations

from typing import Iterator, Type, TypeVar

T = TypeVar("T")
EntityId = int


class EntityRegistry:
    def __init__(self) -> None:
        self._next_id: EntityId = 0
        self._components: dict[EntityId, dict[type, object]] = {}

    def create(self) -> EntityId:
        eid = self._next_id
        self._next_id += 1
        self._components[eid] = {}
        return eid

    def destroy(self, eid: EntityId) -> None:
        self._components.pop(eid, None)

    def add(self, eid: EntityId, component: object) -> None:
        self._components[eid][type(component)] = component

    def get(self, eid: EntityId, comp_type: Type[T]) -> T | None:
        return self._components.get(eid, {}).get(comp_type)  # type: ignore[return-value]

    def query(self, comp_type: Type[T]) -> Iterator[tuple[EntityId, T]]:
        for eid, bag in self._components.items():
            if comp_type in bag:
                yield eid, bag[comp_type]  # type: ignore[misc]

    def all_ids(self) -> list[EntityId]:
        return list(self._components.keys())
