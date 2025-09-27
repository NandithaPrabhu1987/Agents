from typing import Dict

class RuleBasedAIService:
    """Encapsulates the rule-based AI response generation for inventory chat"""
    @staticmethod
    def generate_smart_response(query: str, context: Dict) -> str:
        q = query.lower()
        store_data = context.get("store_data", [])
        critical = [s for s in store_data if s["status"] in ["critical", "stockout"]]
        overstock = [s for s in store_data if s["status"] == "overstock"]

        if any(w in q for w in ["urgent", "critical", "emergency", "immediate"]):
            if critical:
                resp = "**🚨 URGENT INVENTORY ALERT**\n\n"
                resp += f"{len(critical)} stores need immediate attention:\n\n"
                for st in critical:
                    resp += f"• **{st['store_name']}** ({st['location']}) - {st['current_stock']} units, DoI {st['days_of_inventory']}\n"
                if overstock:
                    resp += "\nImmediate transfers from surplus locations:\n"
                    for st in overstock[:3]:
                        resp += f"• {st['store_name']} has {st['current_stock']} units\n"
                return resp
            return "✅ No urgent transfers required."

        if any(w in q for w in ["monsoon", "rain", "weather"]):
            coastal = [s for s in store_data if s["location"] in ["Mumbai", "Chennai", "Kochi"]]
            resp = "**🌧️ MONSOON SEASON STRATEGY**\n\n"
            for st in coastal:
                resp += f"• {st['store_name']}: {st['current_stock']} units (Demand {st['demand_score']}/10)\n"
            resp += "\nRecommendations: boost monsoon gear 30-50% in coastal cities."
            return resp

        if any(w in q for w in ["festive", "diwali", "festival"]):
            metros = [s for s in store_data if s["location"] in ["Delhi", "Mumbai", "Bangalore", "Chennai"]]
            resp = "**🪔 FESTIVE SEASON DISTRIBUTION**\n\n"
            for st in metros:
                resp += f"• {st['store_name']}: {st['current_stock']} units\n"
            resp += "\nIncrease festive inventory 40-60% in metros."
            return resp

        if any(w in q for w in ["transfer", "move", "relocate", "roi"]):
            if critical and overstock:
                resp = "**🚚 TOP TRANSFER OPPORTUNITIES**\n\n"
                for i, (d, s) in enumerate(zip(critical[:3], overstock[:3])):
                    resp += f"{i+1}. {s['store_name']} → {d['store_name']} (50-100 units)\n"
                return resp
            return "Inventory levels look balanced."

        # Overview
        resp = "**📊 INVENTORY SYSTEM OVERVIEW**\n\n"
        by_status = {}
        for st in store_data:
            by_status[st["status"]] = by_status.get(st["status"], 0) + 1
        for k, v in by_status.items():
            resp += f"• {k.title()}: {v} stores\n"
        return resp
