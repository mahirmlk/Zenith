"""Provider pricing snapshots used only to bound pre-call reservations.

Chat snapshot source: https://openrouter.ai/api/v1/models, fetched 2026-11-13.
Prices are USD per token, copied from each model's `pricing.prompt` and
`pricing.completion` fields. Runtime settlement always uses OpenRouter's
reported generation cost; a missing catalog entry fails closed.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING

CATALOG_VERSION = "openrouter-models-2026-11-13"
CATALOG_SOURCE = "https://openrouter.ai/api/v1/models"
CATALOG_SNAPSHOT_DATE = "2026-11-13"


@dataclass(frozen=True)
class ModelPrice:
    prompt_usd_per_token: Decimal
    completion_usd_per_token: Decimal
    context_tokens: int
    max_completion_tokens: int

    @property
    def max_price_prompt_usd_per_million(self) -> float:
        return float(self.prompt_usd_per_token * 1_000_000)

    @property
    def max_price_completion_usd_per_million(self) -> float:
        return float(self.completion_usd_per_token * 1_000_000)

    def maximum_cost_micros(self, max_output_tokens: int, input_token_bound: int) -> int:
        output_limit = min(max_output_tokens, self.max_completion_tokens)
        if not 0 <= input_token_bound <= self.context_tokens:
            raise ValueError("Input token bound exceeds the verified model context")
        # The caller serializes and bounds its actual messages before admission.
        max_usd = (
            Decimal(input_token_bound) * self.prompt_usd_per_token
            + Decimal(output_limit) * self.completion_usd_per_token
        )
        return int((max_usd * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


# Rates and bounds are copied from the source API snapshot named above. Models
# omitted from this mapping cannot be invoked while spend enforcement is active.
MODEL_PRICES: dict[str, ModelPrice] = {
    "anthropic/claude-opus-5.5": ModelPrice(Decimal("0.000004"), Decimal("0.000020"), 1_000_000, 128_000),
    "anthropic/claude-sonnet-5.5": ModelPrice(Decimal("0.000002"), Decimal("0.000010"), 1_000_000, 128_000),
    "openai/gpt-4o": ModelPrice(Decimal("0.0000025"), Decimal("0.000010"), 128_000, 16_384),
    "openai/gpt-4o-mini": ModelPrice(Decimal("0.00000015"), Decimal("0.00000060"), 128_000, 16_384),
    "google/gemini-3.6-flash": ModelPrice(Decimal("0.00000075"), Decimal("0.00000375"), 1_048_576, 65_536),
    "meta-llama/llama-3.3-70b-instruct": ModelPrice(Decimal("0.00000071"), Decimal("0.00000071"), 131_072, 115_200),
}


# OpenAI model page snapshot, 2026-11-13: $0.02 per 1M input tokens.
# https://developers.openai.com/api/docs/models/text-embedding-3-small
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_CATALOG_VERSION = "openai-text-embedding-3-small-2026-11-13"
EMBEDDING_PRICE_USD_PER_TOKEN = Decimal("0.00000002")


def embedding_cost_micros(tokens: int) -> int:
    if tokens < 0:
        raise ValueError("Token usage must be non-negative")
    return int(
        (Decimal(tokens) * EMBEDDING_PRICE_USD_PER_TOKEN * 1_000_000)
        .to_integral_value(rounding=ROUND_CEILING)
    )
