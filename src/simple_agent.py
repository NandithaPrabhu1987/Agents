from __future__ import annotations
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, Tuple

STATE_DIR = Path("logs/simple_agent")
STATE_FILE = STATE_DIR / "state.json"


def _ensure_dirs():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class SimpleInventoryState:
    week: int = 0
    store1_stock: int = 100
    store2_stock: int = 200
    demand_s1: int = 0
    demand_s2: int = 0
    last_transfer: Dict[str, Any] = None  # {"from": "s2", "to": "s1", "moved": 10}
    last_unmet: Dict[str, int] = None  # {"s1": int, "s2": int}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_file() -> "SimpleInventoryState":
        _ensure_dirs()
        if not STATE_FILE.exists():
            return SimpleInventoryState()
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            # tolerate old files by discarding unknown fields
            known = {k: data.get(k) for k in [
                "week","store1_stock","store2_stock","demand_s1","demand_s2","last_transfer","last_unmet"
            ]}
            # fill defaults if missing
            for k, v in SimpleInventoryState().__dict__.items():
                if known.get(k) is None:
                    known[k] = v
            return SimpleInventoryState(**known)
        except Exception:
            return SimpleInventoryState()

    def save(self) -> None:
        _ensure_dirs()
        STATE_FILE.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


class SimpleInventoryAgent:
    """2-store inventory simulator (LLM-only explicit transfers).

    Behavior:
    - State keeps stocks for S1,S2 and weekly demands demand_s1,demand_s2.
    - step_week() ONLY consumes weekly demand; no implicit transfers.
    - transfer() explicitly moves units between S1 and S2, clamped by donor surplus (stock - its demand).
    """

    def __init__(self):
        self.state = SimpleInventoryState.from_file()

    def reset(self) -> Dict[str, Any]:
        self.state = SimpleInventoryState()
        self.state.save()
        return {"ok": True, "message": "State reset", "state": self.state.to_dict()}

    def set_demand(self, s1: int, s2: int) -> Dict[str, Any]:
        self.state.demand_s1 = max(0, int(s1))
        self.state.demand_s2 = max(0, int(s2))
        self.state.save()
        return {
            "ok": True,
            "message": f"Weekly demand set: S1={self.state.demand_s1}, S2={self.state.demand_s2}",
            "state": self.state.to_dict(),
        }

    def status(self) -> Dict[str, Any]:
        return {"ok": True, "state": self.state.to_dict()}

    def _get_stock_ref(self, code: str):
        key = str(code).strip().lower()
        if key in ("s1", "store1", "1"): return "store1_stock"
        if key in ("s2", "store2", "2"): return "store2_stock"
        raise ValueError("unknown store: " + str(code))

    def _ref_to_code(self, ref: str) -> str:
        if ref == "store1_stock": return "s1"
        if ref == "store2_stock": return "s2"
        return ref

    def transfer(self, src: str, dst: str, amount: int) -> Dict[str, Any]:
        if amount is None:
            amount = 0
        qty = max(0, int(amount))
        if qty == 0:
            return {"ok": True, "message": "No transfer (0 qty)", "moved": 0, "state": self.state.to_dict()}
        src_key = self._get_stock_ref(src)
        dst_key = self._get_stock_ref(dst)
        if src_key == dst_key:
            return {"ok": True, "message": "No transfer (same store)", "moved": 0, "state": self.state.to_dict()}
        # donor surplus = max(stock - its own demand, 0)
        if src_key == "store1_stock":
            donor_demand = self.state.demand_s1
        else:
            donor_demand = self.state.demand_s2
        available = getattr(self.state, src_key)
        surplus = max(0, available - donor_demand)
        moved = min(qty, surplus)
        setattr(self.state, src_key, available - moved)
        setattr(self.state, dst_key, getattr(self.state, dst_key) + moved)
        self.state.last_transfer = {"from": src_key, "to": dst_key, "moved": moved}
        self.state.save()
        transfer_obj = {"from": self._ref_to_code(src_key), "to": self._ref_to_code(dst_key), "amount": moved}
        msg = f"Transferred {moved} from {src} to {dst}" + (" (limited by donor surplus)" if moved < qty else "")
        return {"ok": True, "message": msg, "moved": moved, "transfer": transfer_obj, "surplus": surplus, "state": self.state.to_dict()}

    def step_week(self, weeks: int = 1) -> Dict[str, Any]:
        weeks = max(1, int(weeks))
        timeline = []
        for _ in range(weeks):
            details = {"week": self.state.week + 1}
            # capture start-of-week stocks
            start1 = self.state.store1_stock
            start2 = self.state.store2_stock
            # Consume demand at each store (no auto-transfers)
            unmet_s1 = 0
            unmet_s2 = 0
            # compute consumed amounts (bounded by start stock)
            consumed_s1 = min(start1, self.state.demand_s1)
            consumed_s2 = min(start2, self.state.demand_s2)

            if self.state.store1_stock >= self.state.demand_s1:
                self.state.store1_stock -= self.state.demand_s1
            else:
                unmet_s1 = self.state.demand_s1 - self.state.store1_stock
                self.state.store1_stock = 0

            if self.state.store2_stock >= self.state.demand_s2:
                self.state.store2_stock -= self.state.demand_s2
            else:
                unmet_s2 = self.state.demand_s2 - self.state.store2_stock
                self.state.store2_stock = 0

            self.state.week += 1
            self.state.last_unmet = {"s1": unmet_s1, "s2": unmet_s2}
            details["consumed"] = {"s1": consumed_s1, "s2": consumed_s2}
            details["unmet_demand"] = self.state.last_unmet
            details["stocks_start_of_week"] = {"store1": start1, "store2": start2}
            details["stocks_end_of_week"] = {
                "store1": self.state.store1_stock,
                "store2": self.state.store2_stock,
            }
            timeline.append(details)
        self.state.save()
        return {"ok": True, "message": f"Simulated {weeks} week(s)", "timeline": timeline, "state": self.state.to_dict()}

    # -------- Prompt interface (deprecated in LLM-only mode) --------
    def handle_prompt(self, prompt: str) -> Tuple[str, Dict[str, Any]]:
        return ("LLM-only mode: use LLM endpoints.", {"ok": False})
