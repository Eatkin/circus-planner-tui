from __future__ import annotations

import random
from dataclasses import dataclass
from dataclasses import field


@dataclass
class Modifier:
    id: str
    name: str
    additive: bool = False
    requires_equipment_type: str | None = None
    requires_quantity: int = 0


@dataclass
class Equipment:
    id: str
    name: str
    prop_type: str
    quantity: int = 1
    is_default: bool = True


@dataclass
class ResolvedExercise:
    exercise: Exercise
    equipment: Equipment | None
    modifiers: list[Modifier]


@dataclass
class Exercise:
    id: str
    name: str
    prop_type: str
    quantity_needed: int = 0
    comfort: int = 5
    priority: int = 0
    practicing: bool = False
    always_modify: bool = False
    description: str = ""
    modifiers: list[Modifier] = field(default_factory=list)
    available_equipment: list[Equipment] = field(default_factory=list)
    required_equipment: list[Equipment] = field(default_factory=list)

    @classmethod
    def from_db(cls, row: dict) -> Exercise:
        return cls(
            id=row["exercise"]["id"],
            name=row["exercise"]["name"],
            prop_type=row["exercise"]["prop_type"],
            quantity_needed=row["exercise"]["quantity_needed"],
            comfort=row["exercise"]["comfort"],
            priority=row["exercise"]["priority"],
            practicing=bool(row["exercise"]["practicing"]),
            always_modify=bool(row["exercise"]["always_modify"]),
            description=row["exercise"]["description"] or "",
            modifiers=[Modifier(**m) for m in row["modifiers"]],
            available_equipment=[Equipment(**e) for e in row["available_equipment"]],
            required_equipment=[Equipment(**e) for e in row["required_equipment"]],
        )

    def __str__(self) -> str:
        lines = [f"{self.name} ({self.prop_type}, comfort {self.comfort}/10)"]
        if self.description:
            lines.append(f"  {self.description}")
        if self.modifiers:
            lines.append(f"  Modifiers: {', '.join(m.name for m in self.modifiers)}")
        if self.required_equipment:
            lines.append(
                f"  Requires: {', '.join(e.name for e in self.required_equipment)}"
            )
        return "\n".join(lines)

    def _resolve_equipment(self, equipment_swap_chance: float) -> Equipment | None:
        if self.prop_type in ("ball", "club", "ring"):
            defaults = [e for e in self.available_equipment if e.is_default]
            non_defaults = [e for e in self.available_equipment if not e.is_default]
            if non_defaults and random.random() < equipment_swap_chance:
                equipment = random.choice(non_defaults)
            elif defaults:
                equipment = defaults[0]
            else:
                equipment = (
                    self.available_equipment[0] if self.available_equipment else None
                )
        else:
            equipment = (
                random.choice(self.required_equipment)
                if self.required_equipment
                else None
            )
        return equipment

    def _resolve_modifiers(self, modifier_chance: float) -> list[Modifier]:
        # modifiers - always_modify guarantees at least one
        non_additive = [m for m in self.modifiers if not m.additive]
        additive = [m for m in self.modifiers if m.additive]

        chosen = []

        # Nice of the princess to invite us for a picnic, gay Luigi
        # I hope she made lotsa spaghetti
        if random.random() < modifier_chance:
            # Try add a non-additive modifier
            if non_additive:
                chosen.append(random.choice(non_additive))
                # Smaller chance of stacking modifiers
                if additive and random.random() < modifier_chance**2:
                    chosen.append(random.choice(additive))
            elif additive and random.random() < modifier_chance:
                # no non-additive, but maybe just an additive
                chosen.append(random.choice(additive))

        if self.always_modify and not chosen and self.modifiers:
            chosen.append(random.choice(self.modifiers))
        return chosen

    def resolve(
        self,
        modifier_chance: float = 0.4,
        equipment_swap_chance: float = 0.1,
    ) -> ResolvedExercise:
        equipment = self._resolve_equipment(equipment_swap_chance)
        modifiers = self._resolve_modifiers(modifier_chance)

        return ResolvedExercise(
            exercise=self,
            equipment=equipment,
            modifiers=modifiers,
        )

    def extract_core_pattern(self) -> str:
        """Extract siteswap identity from siteswap string - removes entry / exit throws"""
        if "siteswap" not in self.prop_type:
            raise ValueError("Tried to extract siteswap identity from non-siteswap exercise")

        parts = self.id.split("_")
        if len(parts) == 3:
            return parts[1]  # "4_5151_2" -> "5151"
        return parts[0]      # "5151" -> "5151"
