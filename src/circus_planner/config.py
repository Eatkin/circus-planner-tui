from dataclasses import dataclass
from dataclasses import field


@dataclass
class Config:
    # Equipment IDs that are disabled for this session
    disabled_equipment: list[str] = field(default_factory=list)
    # 0-10, how often drills are inserted
    drill_frequency: int = 3
    # 0-10, how often siteswaps are inserted
    siteswap_frequency: int = 3
    # 0.0-1.0, chance of a modifier being applied
    modifier_frequency: float = 0.4
    # -5 to +5, negative = easy session, positive = hard
    difficulty_bias: int = 0


# Global singleton
CONFIG = Config()
