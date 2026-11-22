"""SAI Agents — production-ready KafCa E+Im+Bl agent suite.

KafCa = Kafka for Event sourcing (E) + Impact tracking (Im) + Bl (Blacklist +
Circuit Breaker) for safe self-evolution. The suite generates clean, structured
evolution signals (insights, recommendations, fitness scores) that can be
consumed directly by ``evo-metaclaw`` / ``evolved-skill-opt`` runs.
"""

from sai_agents.config import Settings, get_settings

__version__ = "0.1.0+kafca"

__all__ = ["Settings", "get_settings", "__version__"]
