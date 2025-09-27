import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from enum import Enum
import math

class StoreLocation(str, Enum):
    BANGALORE = "Bangalore"
    MYSORE = "Mysore"
    CHENNAI = "Chennai"
    COIMBATORE = "Coimbatore"
    HYDERABAD = "Hyderabad"
    MUMBAI = "Mumbai"
    PUNE = "Pune"
    DELHI = "Delhi"
    GURGAON = "Gurgaon"
    KOCHI = "Kochi"

class InventoryStatus(str, Enum):
    OVERSTOCK = "overstock"
    BALANCED = "balanced"
    LOW_STOCK = "low_stock"
    CRITICAL = "critical"
    STOCKOUT = "stockout"

class TransferPriority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class ProductType(str, Enum):
    MONSOON_GEAR = "monsoon_gear"
    FESTIVE_WEAR = "festive_wear"
    SUMMER_ESSENTIALS = "summer_essentials"
    WINTER_WEAR = "winter_wear"
    ELECTRONICS = "electronics"
    HOME_DECOR = "home_decor"
    FOOTWEAR = "footwear"
    ACCESSORIES = "accessories"

class Store(BaseModel):
    id: str
    name: str
    location: StoreLocation
    current_stock: int = Field(ge=0, description="Current inventory count")
    min_stock_level: int = Field(ge=0, description="Minimum stock threshold")
    max_capacity: int = Field(gt=0, description="Maximum storage capacity")
    monthly_demand: int = Field(ge=0, description="Average monthly demand")
    sales_last_30_days: int = Field(ge=0, description="Units sold in last 30 days")
    demand_score: float = Field(ge=0, le=10, description="Market demand score (1-10)")
    operational_cost_per_unit: float = Field(ge=0, description="Cost per unit to maintain inventory")

class Product(BaseModel):
    id: str
    name: str
    category: ProductType
    unit_cost: float = Field(gt=0, description="Cost per unit in rupees")
    selling_price: float = Field(gt=0, description="Current selling price")
    shelf_life_days: int = Field(gt=0, description="Product shelf life in days", default=365)
    seasonal_factor: float = Field(ge=0.1, le=3.0, default=1.0, description="Seasonal demand multiplier")
    
class TransferRequest(BaseModel):
    id: str
    product_id: str
    from_store_id: str
    to_store_id: str
    quantity: int = Field(gt=0, description="Units to transfer")
    priority: TransferPriority
    requested_date: datetime
    expected_delivery_date: datetime
    transport_cost_per_unit: float = Field(ge=0)
    status: str = Field(default="pending")

class InventoryAgent:
    """AI-powered Supply Chain Inventory Rebalancing Agent for retail stores"""
    
    def __init__(self):
        self.TRANSFER_COST_PER_KM = 2.5  # ₹2.5 per unit per km
        self.MIN_TRANSFER_QUANTITY = 10  # Minimum economical transfer quantity
        self.SAFETY_STOCK_FACTOR = 0.2  # 20% safety stock
        
        # Distance matrix between major Indian cities (in km) - Realistic road distances
        self.DISTANCE_MATRIX = {
            ("Bangalore", "Mysore"): 140,
            ("Bangalore", "Chennai"): 350,
            ("Bangalore", "Coimbatore"): 365,
            ("Bangalore", "Hyderabad"): 570,
            ("Bangalore", "Mumbai"): 980,
            ("Bangalore", "Pune"): 840,
            ("Bangalore", "Delhi"): 2150,
            ("Bangalore", "Gurgaon"): 2170,
            ("Bangalore", "Kochi"): 550,
            
            ("Chennai", "Coimbatore"): 510,
            ("Chennai", "Kochi"): 680,
            ("Chennai", "Hyderabad"): 630,
            ("Chennai", "Mumbai"): 1340,
            ("Chennai", "Delhi"): 2180,
            
            ("Mumbai", "Pune"): 150,
            ("Mumbai", "Delhi"): 1400,
            ("Mumbai", "Gurgaon"): 1420,
            ("Mumbai", "Hyderabad"): 710,
            ("Mumbai", "Kochi"): 1360,
            
            ("Delhi", "Gurgaon"): 30,
            ("Delhi", "Pune"): 1480,
            ("Delhi", "Hyderabad"): 1570,
            
            ("Hyderabad", "Pune"): 560,
            ("Hyderabad", "Kochi"): 1000,
            
            ("Pune", "Kochi"): 1100,
            ("Coimbatore", "Kochi"): 190,
            ("Mysore", "Kochi"): 380,
            ("Mysore", "Chennai"): 480
        }
        
        # Coordinates for fallback distance computation (lat, lon)
        self.CITY_COORDS = {
            "Bangalore": (12.9716, 77.5946),
            "Mysore": (12.2958, 76.6394),
            "Chennai": (13.0827, 80.2707),
            "Coimbatore": (11.0168, 76.9558),
            "Hyderabad": (17.3850, 78.4867),
            "Mumbai": (19.0760, 72.8777),
            "Pune": (18.5204, 73.8567),
            "Delhi": (28.6139, 77.2090),
            "Gurgaon": (28.4595, 77.0266),
            "Kochi": (9.9312, 76.2673)
        }
    
    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Great-circle distance between two points (km)"""
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    
    def get_distance_between_stores(self, location1: StoreLocation, location2: StoreLocation) -> int:
        """Get distance between two store locations. Uses matrix, else computes fallback road distance."""
        if location1 == location2:
            return 5  # same city default intra-city distance
        key1 = (location1.value, location2.value)
        key2 = (location2.value, location1.value)
        if key1 in self.DISTANCE_MATRIX:
            return self.DISTANCE_MATRIX[key1]
        if key2 in self.DISTANCE_MATRIX:
            return self.DISTANCE_MATRIX[key2]
        # Fallback: compute from coordinates and approximate road factor
        c1 = self.CITY_COORDS.get(location1.value)
        c2 = self.CITY_COORDS.get(location2.value)
        if c1 and c2:
            crow_km = self._haversine_km(c1[0], c1[1], c2[0], c2[1])
            road_km = crow_km * 1.25  # rough road factor multiplier
            return int(round(road_km / 10.0) * 10)  # round to nearest 10 km
        # Default conservative distance if data missing
        return 600
    
    def analyze_store_inventory_status(self, store: Store) -> Dict:
        """Analyze inventory status for a single store"""
        
        # Calculate inventory metrics
        if store.monthly_demand > 0:
            days_of_inventory = (store.current_stock / store.monthly_demand) * 30
            turnover_rate = store.monthly_demand / 30
        else:
            days_of_inventory = float('inf')
            turnover_rate = 0
        
        # Determine inventory status
        if store.current_stock == 0:
            status = InventoryStatus.STOCKOUT
            urgency = TransferPriority.URGENT
        elif store.current_stock < store.min_stock_level:
            status = InventoryStatus.CRITICAL
            urgency = TransferPriority.URGENT
        elif store.current_stock < store.min_stock_level * 1.5:
            status = InventoryStatus.LOW_STOCK
            urgency = TransferPriority.HIGH
        elif store.current_stock > store.max_capacity * 0.8:
            status = InventoryStatus.OVERSTOCK
            urgency = TransferPriority.MEDIUM
        else:
            status = InventoryStatus.BALANCED
            urgency = TransferPriority.LOW
        
        # Calculate optimal stock level
        safety_stock = int(store.min_stock_level * (1 + self.SAFETY_STOCK_FACTOR))
        optimal_stock = min(safety_stock * 2, store.max_capacity)
        
        return {
            "store_id": store.id,
            "store_name": store.name,
            "location": store.location.value,
            "current_stock": store.current_stock,
            "status": status.value,
            "urgency": urgency.value,
            "days_of_inventory": round(days_of_inventory, 1) if days_of_inventory != float('inf') else "∞",
            "optimal_stock": optimal_stock,
            "stock_gap": optimal_stock - store.current_stock,
            "demand_score": store.demand_score,
            "utilization_percent": round((store.current_stock / store.max_capacity) * 100, 1)
        }
    
    def recommend_inventory_transfers(self, stores: List[Store], product: Product) -> List[Dict]:
        """Recommend optimal inventory transfers between stores"""
        
        # Analyze all stores
        store_analyses = [self.analyze_store_inventory_status(store) for store in stores]
        
        # Identify stores needing inventory (sorted by urgency and demand)
        deficit_stores = [
            analysis for analysis in store_analyses 
            if analysis["status"] in ["critical", "low_stock", "stockout"] and analysis["stock_gap"] > 0
        ]
        deficit_stores.sort(key=lambda x: (x["urgency"] == "urgent", x["demand_score"]), reverse=True)
        
        # Identify stores with excess inventory
        surplus_stores = [
            analysis for analysis in store_analyses 
            if analysis["status"] == "overstock" or analysis["current_stock"] > analysis["optimal_stock"]
        ]
        surplus_stores.sort(key=lambda x: x["current_stock"] - x["optimal_stock"], reverse=True)
        
        transfer_recommendations = []
        
        # Generate transfer recommendations
        for deficit_store in deficit_stores:
            needed_quantity = abs(deficit_store["stock_gap"])
            
            if needed_quantity < self.MIN_TRANSFER_QUANTITY:
                continue
                
            for surplus_store in surplus_stores:
                available_quantity = surplus_store["current_stock"] - surplus_store["optimal_stock"]
                
                if available_quantity < self.MIN_TRANSFER_QUANTITY:
                    continue
                
                # Calculate transfer quantity
                transfer_qty = min(needed_quantity, available_quantity, needed_quantity)
                
                if transfer_qty < self.MIN_TRANSFER_QUANTITY:
                    continue
                
                # Calculate costs and benefits
                distance = self.get_distance_between_stores(
                    StoreLocation(surplus_store["location"]), 
                    StoreLocation(deficit_store["location"])
                )
                transport_cost = transfer_qty * distance * self.TRANSFER_COST_PER_KM
                potential_revenue = transfer_qty * product.selling_price
                
                # Calculate delivery time (assuming 50 km/hour average speed)
                delivery_hours = distance / 50
                delivery_date = datetime.now() + timedelta(hours=delivery_hours)
                
                transfer_recommendations.append({
                    "from_store": surplus_store["store_name"],
                    "from_location": surplus_store["location"],
                    "to_store": deficit_store["store_name"], 
                    "to_location": deficit_store["location"],
                    "product_id": product.id,
                    "product_name": product.name,
                    "transfer_quantity": transfer_qty,
                    "distance_km": distance,
                    "transport_cost": round(transport_cost, 2),
                    "potential_revenue": round(potential_revenue, 2),
                    "roi_ratio": round(potential_revenue / max(transport_cost, 1), 2),
                    "priority": deficit_store["urgency"],
                    "estimated_delivery": delivery_date.strftime("%Y-%m-%d %H:%M"),
                    "source_after_transfer": surplus_store["current_stock"] - transfer_qty,
                    "destination_after_transfer": deficit_store["current_stock"] + transfer_qty
                })
                
                # Update quantities for next iteration
                surplus_store["current_stock"] -= transfer_qty
                deficit_store["current_stock"] += transfer_qty
                needed_quantity -= transfer_qty
                
                if needed_quantity <= 0:
                    break
        
        # Sort recommendations by ROI and priority
        transfer_recommendations.sort(
            key=lambda x: (x["priority"] == "urgent", x["roi_ratio"]), 
            reverse=True
        )
        
        return transfer_recommendations[:10]  # Return top 10 recommendations
    
    def seasonal_inventory_optimization(self, stores: List[Store], product: Product, 
                                      season: str = None) -> Dict:
        """Optimize inventory distribution for seasonal demands"""
        
        current_month = datetime.now().month
        
        # Define seasonal patterns
        seasonal_multipliers = {
            "monsoon": {
                "peak_months": [6, 7, 8, 9],
                "locations": {
                    "Bangalore": 1.3, "Mysore": 1.2, "Chennai": 1.4,
                    "Kochi": 1.5, "Mumbai": 1.6, "Pune": 1.3
                }
            },
            "festive": {
                "peak_months": [10, 11, 12],
                "locations": {
                    "Delhi": 1.5, "Mumbai": 1.4, "Bangalore": 1.3,
                    "Hyderabad": 1.3, "Chennai": 1.2
                }
            },
            "summer": {
                "peak_months": [3, 4, 5],
                "locations": {
                    "Chennai": 1.4, "Hyderabad": 1.3, "Mumbai": 1.2,
                    "Delhi": 1.5, "Pune": 1.2
                }
            }
        }
        
        # Auto-detect season if not provided
        if not season:
            if current_month in [6, 7, 8, 9]:
                season = "monsoon"
            elif current_month in [10, 11, 12]:
                season = "festive"
            elif current_month in [3, 4, 5]:
                season = "summer"
            else:
                season = "normal"
        
        multipliers = seasonal_multipliers.get(season, {})
        location_factors = multipliers.get("locations", {})
        
        # Calculate seasonal demand adjustments
        seasonal_analysis = []
        for store in stores:
            location_multiplier = location_factors.get(store.location.value, 1.0)
            adjusted_demand = store.monthly_demand * location_multiplier * product.seasonal_factor
            recommended_stock = int(adjusted_demand * 1.2)  # 20% buffer
            
            seasonal_analysis.append({
                "store_name": store.name,
                "location": store.location.value,
                "current_stock": store.current_stock,
                "current_demand": store.monthly_demand,
                "seasonal_multiplier": location_multiplier,
                "adjusted_demand": round(adjusted_demand, 0),
                "recommended_stock": recommended_stock,
                "adjustment_needed": recommended_stock - store.current_stock
            })
        
        return {
            "season": season,
            "product_id": product.id,
            "analysis_date": datetime.now().isoformat(),
            "store_analysis": seasonal_analysis,
            "total_adjustment_needed": sum(s["adjustment_needed"] for s in seasonal_analysis),
            "stores_needing_stock": [s for s in seasonal_analysis if s["adjustment_needed"] > 0],
            "stores_with_excess": [s for s in seasonal_analysis if s["adjustment_needed"] < -10]
        }
    
    def generate_transfer_schedule(self, transfer_recommendations: List[Dict], 
                                 max_daily_transfers: int = 5) -> Dict:
        """Generate optimized transfer schedule"""
        
        # Sort by priority and ROI
        sorted_transfers = sorted(
            transfer_recommendations,
            key=lambda x: (x["priority"] == "urgent", x["roi_ratio"]),
            reverse=True
        )
        
        schedule = []
        current_date = datetime.now()
        daily_transfers = 0
        
        for i, transfer in enumerate(sorted_transfers):
            if daily_transfers >= max_daily_transfers:
                current_date += timedelta(days=1)
                daily_transfers = 0
            
            schedule_entry = {
                **transfer,
                "scheduled_date": current_date.strftime("%Y-%m-%d"),
                "schedule_order": i + 1,
                "batch_number": math.ceil((i + 1) / max_daily_transfers)
            }
            
            schedule.append(schedule_entry)
            daily_transfers += 1
        
        return {
            "total_transfers": len(schedule),
            "total_days_required": math.ceil(len(schedule) / max_daily_transfers),
            "total_transport_cost": sum(t["transport_cost"] for t in schedule),
            "total_potential_revenue": sum(t["potential_revenue"] for t in schedule),
            "average_roi": round(
                sum(t["roi_ratio"] for t in schedule) / len(schedule) if schedule else 0, 2
            ),
            "urgent_transfers": len([t for t in schedule if t["priority"] == "urgent"]),
            "schedule": schedule
        }
    
    def comprehensive_inventory_analysis(self, stores: List[Store], products: List[Product]) -> Dict:
        """Perform comprehensive inventory analysis across all stores and products"""
        
        analysis = {
            "analysis_date": datetime.now().isoformat(),
            "total_stores": len(stores),
            "total_products": len(products),
            "store_summaries": [],
            "product_summaries": [],
            "critical_alerts": [],
            "recommended_actions": []
        }
        
        # Analyze each store
        for store in stores:
            store_analysis = self.analyze_store_inventory_status(store)
            analysis["store_summaries"].append(store_analysis)
            
            if store_analysis["status"] in ["critical", "stockout"]:
                analysis["critical_alerts"].append({
                    "type": "CRITICAL_STOCK",
                    "store": store.name,
                    "message": f"{store.name} has {store_analysis['status']} inventory status",
                    "urgency": "HIGH"
                })
        
        # Analyze transfers for each product
        for product in products:
            transfer_recs = self.recommend_inventory_transfers(stores, product)
            
            if transfer_recs:
                analysis["product_summaries"].append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "transfer_opportunities": len(transfer_recs),
                    "total_potential_revenue": sum(t["potential_revenue"] for t in transfer_recs),
                    "total_transport_cost": sum(t["transport_cost"] for t in transfer_recs),
                    "top_recommendations": transfer_recs[:3]
                })
        
        # Generate actionable recommendations
        urgent_transfers = []
        high_roi_transfers = []
        
        for product in products:
            transfers = self.recommend_inventory_transfers(stores, product)
            for transfer in transfers:
                if transfer["priority"] == "urgent":
                    urgent_transfers.append(transfer)
                elif transfer["roi_ratio"] > 3.0:
                    high_roi_transfers.append(transfer)
        
        if urgent_transfers:
            analysis["recommended_actions"].append({
                "action": "EXECUTE_URGENT_TRANSFERS",
                "count": len(urgent_transfers),
                "description": f"Execute {len(urgent_transfers)} urgent transfers to prevent stockouts"
            })
        
        if high_roi_transfers:
            analysis["recommended_actions"].append({
                "action": "PRIORITIZE_HIGH_ROI_TRANSFERS", 
                "count": len(high_roi_transfers),
                "description": f"Schedule {len(high_roi_transfers)} high-ROI transfers (ROI > 3.0x)"
            })
        
        return analysis
