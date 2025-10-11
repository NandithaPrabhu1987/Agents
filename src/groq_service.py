import os
import json
import asyncio
from typing import Dict, Any, Optional, List

from groq import Groq
from src.config import get_settings


class GroqInventoryService:
    """LLM-backed inventory analysis using Groq chat completions with optional history and structured outputs."""

    def __init__(self, model: Optional[str] = None):
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set. Export it or add to .env")
        self.client = Groq(api_key=api_key)
        settings = get_settings()
        self.model = settings.groq_model

    async def analyze_inventory_scenario(self, query: str, context: Dict[str, Any], history: Optional[List[Dict[str,str]]] = None) -> str:
        """Generate a grounded, concise analysis for the given inventory query with optional prior history.
        Output is structured: SUMMARY, KEY_METRICS, RECOMMENDATIONS, RISKS, FOLLOW_UP_QUESTION.
        """
        system_prompt = (
            "You are a senior supply chain inventory optimization analyst for a 10-store Indian retail chain. "
            "Respond in concise, data-grounded form ONLY using provided context. "
            "Output sections in this exact order with markdown-style headings (##):\n"
            "## SUMMARY (2-4 bullet lines)\n"
            "## KEY_METRICS (bullet list of quantified facts)\n"
            "## RECOMMENDATIONS (numbered list)\n"
            "## RISKS (bullet list; if none, say 'None material')\n"
            "## FOLLOW_UP_QUESTION (one clarifying question to improve next action)"
        )

        stores = context.get("store_data", [])[:10]
        products = context.get("products", [])[:12]
        compact_context = {"stores": stores, "products": products}

        messages: List[Dict[str,str]] = [{"role": "system", "content": system_prompt}]
        if history:
            # include trimmed prior turns (cap last 6 to reduce token use)
            for m in history[-6:]:
                if m.get("role") in {"user", "assistant"} and m.get("content"):
                    messages.append({"role": m["role"], "content": m["content"][:4000]})
        messages.append({
            "role": "user",
            "content": "Question: " + query + "\n\nContext (JSON):\n" + json.dumps(compact_context, ensure_ascii=False)
        })

        def _call():
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.25,
                max_tokens=800,
                top_p=0.9,
                stream=False,
            )
            return resp.choices[0].message.content.strip()

        return await asyncio.to_thread(_call)

    async def analyze_and_propose_plan(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Ask the model to return a compact JSON proposal for a transfer plan.
        JSON schema (all optional except product or product_id):
        {
          "product": "Monsoon Raincoats Premium",
          "product_id": "<id>",
          "from_stores": ["Mysore", "Kochi"],
          "to_stores": ["Bangalore"],
          "quantity_cap": 60,
          "priority": "urgent|high|medium|low",
          "rationale": ["short bullet 1", "short bullet 2"]
        }
        """
        instruction = (
            "Return ONLY valid JSON matching this schema with no extra text. "
            "Use store names as in the context (e.g., Bangalore, Mysore). "
            "Keep rationale list to max 5 short bullets."
        )
        stores = context.get("store_data", [])[:10]
        products = context.get("products", [])[:12]
        compact_context = {"stores": stores, "products": products}

        messages = [
            {"role": "system", "content": "You generate planning JSON for inventory transfers. Be precise and terse."},
            {"role": "user", "content": instruction + "\n\nQuestion: " + query + "\n\nContext (JSON):\n" + json.dumps(compact_context, ensure_ascii=False)},
        ]

        def _call():
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=500,
                top_p=0.9,
                stream=False,
            )
            text = resp.choices[0].message.content.strip()
            # Try to extract JSON
            candidate = text
            if '```' in text:
                # extract content between backticks if present
                parts = text.split('```')
                for part in parts:
                    part = part.strip()
                    if part.startswith('{') and part.endswith('}'):
                        candidate = part
                        break
            try:
                return json.loads(candidate)
            except Exception:
                # fallback: find first { ... } block
                start = candidate.find('{')
                end = candidate.rfind('}')
                if start != -1 and end != -1 and end > start:
                    try:
                        return json.loads(candidate[start:end+1])
                    except Exception:
                        pass
                raise ValueError("Model did not return valid JSON proposal")

        return await asyncio.to_thread(_call)

    async def refine_previous(self, instruction: str, last_response: str, context: Dict[str, Any]) -> str:
        """Refine a prior assistant response with a user instruction; maintain same section format."""
        system_prompt = (
            "You refine prior inventory analysis. Maintain the SAME section headings: SUMMARY, KEY_METRICS, RECOMMENDATIONS, RISKS, FOLLOW_UP_QUESTION. "
            "Incorporate the user refinement instruction faithfully if it does not contradict provided quantitative context. "
            "If instruction conflicts with data, note the conflict under RISKS and provide safest alternative."
        )
        stores = context.get("store_data", [])[:10]
        products = context.get("products", [])[:12]
        compact_context = {"stores": stores, "products": products}
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                "Refinement Instruction: " + instruction + "\n\nPrevious Assistant Response:\n" + last_response +
                "\n\nContext (JSON):\n" + json.dumps(compact_context, ensure_ascii=False)
            )}
        ]
        def _call():
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.25,
                max_tokens=700,
                top_p=0.9,
                stream=False,
            )
            return resp.choices[0].message.content.strip()
        return await asyncio.to_thread(_call)
