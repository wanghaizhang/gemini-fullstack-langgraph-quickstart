import os
from pydantic import BaseModel, Field
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig


class Configuration(BaseModel):
    """The configuration for the agent."""

    model: Optional[str] = Field(
        default=None,
        metadata={
            "description": (
                "Model chosen by the caller (frontend dropdown). When set it overrides "
                "the per-node model fields for the whole run."
            )
        },
    )

    query_generator_model: str = Field(
        default="gemini-2.0-flash",
        metadata={
            "description": "The name of the language model to use for the agent's query generation."
        },
    )

    reflection_model: str = Field(
        default="gemini-2.5-flash",
        metadata={
            "description": "The name of the language model to use for the agent's reflection."
        },
    )

    answer_model: str = Field(
        default="gemini-2.5-pro",
        metadata={
            "description": "The name of the language model to use for the agent's answer."
        },
    )

    number_of_initial_queries: int = Field(
        default=3,
        metadata={"description": "The number of initial search queries to generate."},
    )

    max_research_loops: int = Field(
        default=2,
        metadata={"description": "The maximum number of research loops to perform."},
    )

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = (
            config["configurable"] if config and "configurable" in config else {}
        )

        # Precedence: per-request configurable > env > field default.
        # (Env used to win here, which silently ignored the frontend model dropdown.)
        raw_values: dict[str, Any] = {
            name: configurable.get(name) or os.environ.get(name.upper())
            for name in cls.model_fields.keys()
        }

        # Filter out None values
        values = {k: v for k, v in raw_values.items() if v is not None}

        return cls(**values)

    def resolve_model(self, node_default: str, state_value: Optional[str] = None) -> str:
        """Model for a node: request config > state input > env/field default."""
        return self.model or state_value or node_default
