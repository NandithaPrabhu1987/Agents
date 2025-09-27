import os
import json
import asyncio
from typing import Dict, Any, Optional

from groq import Groq


class GroqInventoryService:
    """LLM-backed inventory analysis using Groq chat completions."""

    def __init__(self, model: Optional[str] = None):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set. Export it or add to .env")
        self.client = Groq(api_key=api_key)
        self.model = model or os.getenv("GROQ_MODEL", "llama3-70b-8192")

    async def analyze_inventory_scenario(self, query: str, context: Dict[str, Any]) -> str:
        """Generate a grounded, concise analysis for the given inventory query.
        Wrapped in asyncio.to_thread to avoid blocking the event loop.
        """
        system_prompt = (
            "You are an inventory optimization analyst for a 10-store Indian retail chain. "
            "Be concise and actionable. Use only the provided context. "
            "Return: bullet points with reasons, quantities, priority (URGENT/HIGH/MEDIUM), distance/cost/ROI when relevant."
        )

        # Trim context to keep prompt size reasonable
        stores = context.get("store_data", [])[:10]
        products = context.get("products", [])[:12]
        compact_context = {
            "stores": stores,
            "products": products,
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Question: " + query + "\n\n"
                    "Context (JSON):\n" + json.dumps(compact_context, ensure_ascii=False)
                ),
            },
        ]

        def _call():
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                max_tokens=600,
                top_p=0.9,
                stream=False,
            )
            return resp.choices[0].message.content.strip()

        return await asyncio.to_thread(_call)
