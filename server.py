from fastapi import FastAPI, APIRouter, HTTPException, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
from bson import ObjectId
import re

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# ===== MODELS =====

class Location(BaseModel):
    lat: float
    lng: float

class ServiceCreate(BaseModel):
    name: str
    price_inr: int
    duration_minutes: int

class Service(ServiceCreate):
    id: str
    salon_id: str

class SalonCreate(BaseModel):
    name: str
    phone: str
    address: str
    location: Location
    tagline: Optional[str] = ""
    owner_name: str
    owner_phone: str

class SalonUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    location: Optional[Location] = None
    tagline: Optional[str] = None
    banner_base64: Optional[str] = None
    logo_base64: Optional[str] = None
    status: Optional[str] = None  # "free" or "busy"

class Salon(BaseModel):
    id: str
    name: str
    slug: str
    phone: str
    address: str
    location: Location
    tagline: str = ""
    banner_base64: Optional[str] = None
    logo_base64: Optional[str] = None
    status: str = "free"  # "free" or "busy"
    subscription_start: datetime
    is_active: bool = True
    owner_id: str

class OwnerLogin(BaseModel):
    phone: str
    name: str

class OwnerResponse(BaseModel):
    id: str
    name: str
    phone: str
    salon_id: Optional[str] = None

class AdminLogin(BaseModel):
    username: str
    password: str

class QueueJoin(BaseModel):
    salon_id: str
    customer_name: str
    customer_phone: str
    service_id: str

class QueueToken(BaseModel):
    id: str
    salon_id: str
    customer_name: str
    customer_phone: str
    service_id: str
    service_name: str
    service_price: int
    token_number: int
    status: str  # "waiting", "completed", "cancelled"
    created_at: datetime
    completed_at: Optional[datetime] = None
    estimated_wait_minutes: int

class SalonStats(BaseModel):
    total_customers_today: int
    total_customers_all: int
    estimated_earnings_today: int
    estimated_earnings_all: int
    active_queue_count: int

# ===== UTILITY FUNCTIONS =====

def create_slug(name: str) -> str:
    """Create URL-friendly slug from salon name"""
    slug = re.sub(r'[^a-zA-Z0-9\s]', '', name)
    slug = re.sub(r'\s+', '', slug)
    return slug.lower()

def is_subscription_active(subscription_start: datetime) -> bool:
    """Check if 30-day trial is still active"""
    expiry_date = subscription_start + timedelta(days=30)
    return datetime.utcnow() < expiry_date

async def calculate_wait_time(salon_id: str, service_id: str) -> int:
    """Calculate estimated wait time based on queue"""
    # Get all waiting tokens
    waiting_tokens = await db.queue.find({
        "salon_id": salon_id,
        "status": "waiting"
    }).sort("created_at", 1).to_list(100)
    
    total_wait = 0
    for token in waiting_tokens:
        # Get service duration
        service = await db.services.find_one({"_id": ObjectId(token["service_id"])})
        if service:
            total_wait += service.get("duration_minutes", 30)
    
    # Add current service duration
    current_service = await db.services.find_one({"_id": ObjectId(service_id)})
    if current_service:
        total_wait += current_service.get("duration_minutes", 30)
    
    return total_wait

async def get_next_token_number(salon_id: str) -> int:
    """Get next token number for salon"""
    last_token = await db.queue.find_one(
        {"salon_id": salon_id},
        sort=[("token_number", -1)]
    )
    if last_token:
        return last_token["token_number"] + 1
    return 1

# ===== OWNER ROUTES =====

@api_router.post("/owner/login")
async def owner_login(data: OwnerLogin):
    """Login or register owner with phone and name"""
    # Check if owner exists
    owner = await db.owners.find_one({"phone": data.phone})
    
    if owner:
        # Update name if changed
        await db.owners.update_one(
            {"_id": owner["_id"]},
            {"$set": {"name": data.name}}
        )
        salon = await db.salons.find_one({"owner_id": str(owner["_id"])})
        return {
            "id": str(owner["_id"]),
            "name": data.name,
            "phone": data.phone,
            "salon_id": str(salon["_id"]) if salon else None
        }
    
    # Create new owner
    owner_doc = {
        "name": data.name,
        "phone": data.phone,
        "created_at": datetime.utcnow()
    }
    result = await db.owners.insert_one(owner_doc)
    
    return {
        "id": str(result.inserted_id),
        "name": data.name,
        "phone": data.phone,
        "salon_id": None
    }

# ===== SALON ROUTES =====

@api_router.post("/salon")
async def create_salon(data: SalonCreate):
    """Create a new salon"""
    # Check if owner exists
    owner = await db.owners.find_one({"phone": data.owner_phone})
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found. Please login first.")
    
    # Check if owner already has a salon
    existing_salon = await db.salons.find_one({"owner_id": str(owner["_id"])})
    if existing_salon:
        raise HTTPException(status_code=400, detail="Owner already has a salon")
    
    slug = create_slug(data.name)
    
    # Check if slug already exists
    slug_exists = await db.salons.find_one({"slug": slug})
    if slug_exists:
        slug = f"{slug}{str(owner['_id'])[-4:]}"
    
    salon_doc = {
        "name": data.name,
        "slug": slug,
        "phone": data.phone,
        "address": data.address,
        "location": data.location.dict(),
        "tagline": data.tagline,
        "banner_base64": None,
        "logo_base64": None,
        "status": "free",
        "subscription_start": datetime.utcnow(),
        "is_active": True,
        "owner_id": str(owner["_id"]),
        "created_at": datetime.utcnow()
    }
    
    result = await db.salons.insert_one(salon_doc)
    salon_doc["id"] = str(result.inserted_id)
    salon_doc.pop("_id", None)
    
    return salon_doc

@api_router.get("/salon/slug/{slug}")
async def get_salon_by_slug(slug: str):
    """Get salon details by slug"""
    salon = await db.salons.find_one({"slug": slug})
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found")
    
    # Get services
    services = await db.services.find({"salon_id": str(salon["_id"])}).to_list(100)
    
    salon["id"] = str(salon["_id"])
    salon.pop("_id", None)
    
    for service in services:
        service["id"] = str(service["_id"])
        service.pop("_id", None)
    
    return {
        "salon": salon,
        "services": services,
        "subscription_active": is_subscription_active(salon["subscription_start"])
    }

@api_router.get("/salon/{salon_id}")
async def get_salon(salon_id: str):
    """Get salon details by ID"""
    try:
        salon = await db.salons.find_one({"_id": ObjectId(salon_id)})
    except:
        raise HTTPException(status_code=404, detail="Invalid salon ID")
    
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found")
    
    # Get services
    services = await db.services.find({"salon_id": salon_id}).to_list(100)
    
    salon["id"] = str(salon["_id"])
    salon.pop("_id", None)
    
    for service in services:
        service["id"] = str(service["_id"])
        service.pop("_id", None)
    
    return {
        "salon": salon,
        "services": services,
        "subscription_active": is_subscription_active(salon["subscription_start"])
    }

@api_router.put("/salon/{salon_id}")
async def update_salon(salon_id: str, data: SalonUpdate):
    """Update salon details"""
    salon = await db.salons.find_one({"_id": ObjectId(salon_id)})
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found")
    
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    
    if "location" in update_data:
        update_data["location"] = update_data["location"].dict()
    
    if update_data:
        await db.salons.update_one(
            {"_id": ObjectId(salon_id)},
            {"$set": update_data}
        )
    
    updated_salon = await db.salons.find_one({"_id": ObjectId(salon_id)})
    updated_salon["id"] = str(updated_salon["_id"])
    updated_salon.pop("_id", None)
    
    return updated_salon

@api_router.get("/salons/nearby")
async def get_nearby_salons(lat: float = Query(...), lng: float = Query(...), radius_km: float = Query(10)):
    """Get nearby salons based on GPS coordinates"""
    # For MVP, return all active salons sorted by distance
    # In production, use MongoDB geospatial queries
    salons = await db.salons.find({"is_active": True}).to_list(100)
    
    # Calculate distance and sort
    import math
    
    def calculate_distance(lat1, lng1, lat2, lng2):
        """Calculate distance using Haversine formula"""
        R = 6371  # Earth radius in km
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    
    salon_list = []
    for salon in salons:
        distance = calculate_distance(
            lat, lng,
            salon["location"]["lat"],
            salon["location"]["lng"]
        )
        
        if distance <= radius_km:
            salon["id"] = str(salon["_id"])
            salon.pop("_id", None)
            salon["distance_km"] = round(distance, 2)
            salon_list.append(salon)
    
    # Sort by distance
    salon_list.sort(key=lambda x: x["distance_km"])
    
    return salon_list

# ===== SERVICE ROUTES =====

@api_router.post("/service")
async def create_service(data: ServiceCreate, salon_id: str = Query(...)):
    """Add a service to salon"""
    salon = await db.salons.find_one({"_id": ObjectId(salon_id)})
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found")
    
    service_doc = {
        "salon_id": salon_id,
        "name": data.name,
        "price_inr": data.price_inr,
        "duration_minutes": data.duration_minutes,
        "created_at": datetime.utcnow()
    }
    
    result = await db.services.insert_one(service_doc)
    service_doc["id"] = str(result.inserted_id)
    service_doc.pop("_id", None)
    
    return service_doc

@api_router.get("/service/{salon_id}")
async def get_services(salon_id: str):
    """Get all services for a salon"""
    services = await db.services.find({"salon_id": salon_id}).to_list(100)
    
    for service in services:
        service["id"] = str(service["_id"])
        service.pop("_id", None)
    
    return services

@api_router.put("/service/{service_id}")
async def update_service(service_id: str, data: ServiceCreate):
    """Update a service"""
    result = await db.services.update_one(
        {"_id": ObjectId(service_id)},
        {"$set": data.dict()}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Service not found")
    
    service = await db.services.find_one({"_id": ObjectId(service_id)})
    service["id"] = str(service["_id"])
    service.pop("_id", None)
    
    return service

@api_router.delete("/service/{service_id}")
async def delete_service(service_id: str):
    """Delete a service"""
    result = await db.services.delete_one({"_id": ObjectId(service_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Service not found")
    
    return {"message": "Service deleted successfully"}

# ===== QUEUE ROUTES =====

@api_router.post("/queue/join")
async def join_queue(data: QueueJoin):
    """Customer joins the queue"""
    # Check if salon exists and subscription is active
    try:
        salon = await db.salons.find_one({"_id": ObjectId(data.salon_id)})
    except:
        raise HTTPException(status_code=404, detail="Invalid salon ID")
    
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found")
    
    if not salon["is_active"]:
        raise HTTPException(status_code=403, detail="Salon is currently inactive")
    
    if not is_subscription_active(salon["subscription_start"]):
        raise HTTPException(status_code=403, detail="Salon subscription has expired")
    
    # Get service details
    try:
        service = await db.services.find_one({"_id": ObjectId(data.service_id)})
    except:
        raise HTTPException(status_code=404, detail="Invalid service ID")
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    # Calculate wait time
    wait_time = await calculate_wait_time(data.salon_id, data.service_id)
    
    # Get next token number
    token_number = await get_next_token_number(data.salon_id)
    
    # Create queue entry
    queue_doc = {
        "salon_id": data.salon_id,
        "customer_name": data.customer_name,
        "customer_phone": data.customer_phone,
        "service_id": data.service_id,
        "service_name": service["name"],
        "service_price": service["price_inr"],
        "token_number": token_number,
        "status": "waiting",
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "estimated_wait_minutes": wait_time
    }
    
    result = await db.queue.insert_one(queue_doc)
    queue_doc["id"] = str(result.inserted_id)
    queue_doc.pop("_id", None)
    
    # Update salon status to busy
    await db.salons.update_one(
        {"_id": ObjectId(data.salon_id)},
        {"$set": {"status": "busy"}}
    )
    
    return queue_doc

@api_router.get("/queue/{salon_id}")
async def get_queue(salon_id: str):
    """Get queue for a salon"""
    queue = await db.queue.find({
        "salon_id": salon_id,
        "status": "waiting"
    }).sort("token_number", 1).to_list(100)
    
    for token in queue:
        token["id"] = str(token["_id"])
        token.pop("_id", None)
    
    return queue

@api_router.put("/queue/{token_id}/complete")
async def complete_token(token_id: str):
    """Mark a token as completed"""
    result = await db.queue.update_one(
        {"_id": ObjectId(token_id)},
        {"$set": {
            "status": "completed",
            "completed_at": datetime.utcnow()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Check if queue is now empty
    token = await db.queue.find_one({"_id": ObjectId(token_id)})
    remaining = await db.queue.count_documents({
        "salon_id": token["salon_id"],
        "status": "waiting"
    })
    
    if remaining == 0:
        # Update salon status to free
        await db.salons.update_one(
            {"_id": ObjectId(token["salon_id"])},
            {"$set": {"status": "free"}}
        )
    
    return {"message": "Token completed successfully"}

@api_router.get("/queue/token/{token_id}")
async def get_token_status(token_id: str):
    """Get status of a specific token"""
    token = await db.queue.find_one({"_id": ObjectId(token_id)})
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    
    # Recalculate wait time for waiting tokens
    if token["status"] == "waiting":
        # Count tokens ahead in queue
        tokens_ahead = await db.queue.count_documents({
            "salon_id": token["salon_id"],
            "token_number": {"$lt": token["token_number"]},
            "status": "waiting"
        })
        
        # Calculate wait time based on tokens ahead
        wait_time = 0
        ahead_tokens = await db.queue.find({
            "salon_id": token["salon_id"],
            "token_number": {"$lt": token["token_number"]},
            "status": "waiting"
        }).to_list(100)
        
        for ahead_token in ahead_tokens:
            service = await db.services.find_one({"_id": ObjectId(ahead_token["service_id"])})
            if service:
                wait_time += service.get("duration_minutes", 30)
        
        token["estimated_wait_minutes"] = wait_time
        token["tokens_ahead"] = tokens_ahead
    
    token["id"] = str(token["_id"])
    token.pop("_id", None)
    
    return token

# ===== STATS ROUTES =====

@api_router.get("/salon/{salon_id}/stats")
async def get_salon_stats(salon_id: str):
    """Get salon statistics"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Today's customers
    today_customers = await db.queue.count_documents({
        "salon_id": salon_id,
        "created_at": {"$gte": today_start}
    })
    
    # All time customers
    all_customers = await db.queue.count_documents({
        "salon_id": salon_id
    })
    
    # Today's earnings
    today_tokens = await db.queue.find({
        "salon_id": salon_id,
        "created_at": {"$gte": today_start}
    }).to_list(1000)
    
    today_earnings = sum(token.get("service_price", 0) for token in today_tokens)
    
    # All time earnings
    all_tokens = await db.queue.find({
        "salon_id": salon_id
    }).to_list(10000)
    
    all_earnings = sum(token.get("service_price", 0) for token in all_tokens)
    
    # Active queue count
    active_queue = await db.queue.count_documents({
        "salon_id": salon_id,
        "status": "waiting"
    })
    
    return {
        "total_customers_today": today_customers,
        "total_customers_all": all_customers,
        "estimated_earnings_today": today_earnings,
        "estimated_earnings_all": all_earnings,
        "active_queue_count": active_queue
    }

# ===== ADMIN ROUTES =====

@api_router.post("/admin/login")
async def admin_login(data: AdminLogin):
    """Admin login"""
    logger.info(f"Admin login attempt - username: '{data.username}', password length: {len(data.password)}")
    logger.info(f"Comparing username: '{data.username}' == 'admin': {data.username == 'admin'}")
    logger.info(f"Comparing password: '{data.password}' == 'admin123': {data.password == 'admin123'}")
    
    # For MVP, use hardcoded admin credentials
    # In production, use proper password hashing
    if data.username == "admin" and data.password == "admin123":
        logger.info("Admin login successful")
        return {
            "message": "Login successful",
            "role": "admin"
        }
    
    logger.warning(f"Admin login failed - Invalid credentials for username: '{data.username}'")
    raise HTTPException(status_code=401, detail="Invalid credentials")

@api_router.get("/admin/salons")
async def get_all_salons():
    """Get all salons for admin"""
    salons = await db.salons.find().to_list(1000)
    
    for salon in salons:
        salon["id"] = str(salon["_id"])
        salon.pop("_id", None)
        salon["subscription_active"] = is_subscription_active(salon["subscription_start"])
        
        # Get owner details
        owner = await db.owners.find_one({"_id": ObjectId(salon["owner_id"])})
        if owner:
            salon["owner_name"] = owner["name"]
            salon["owner_phone"] = owner["phone"]
    
    return salons

@api_router.put("/admin/salon/{salon_id}/toggle")
async def toggle_salon_status(salon_id: str):
    """Activate or deactivate a salon"""
    salon = await db.salons.find_one({"_id": ObjectId(salon_id)})
    if not salon:
        raise HTTPException(status_code=404, detail="Salon not found")
    
    new_status = not salon["is_active"]
    
    await db.salons.update_one(
        {"_id": ObjectId(salon_id)},
        {"$set": {"is_active": new_status}}
    )
    
    return {
        "message": f"Salon {'activated' if new_status else 'deactivated'} successfully",
        "is_active": new_status
    }

# ===== ROOT ROUTE =====

@api_router.get("/")
async def root():
    return {"message": "QuickSalon API", "version": "1.0.0"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
