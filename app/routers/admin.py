from fastapi import APIRouter, Depends, HTTPException

from ..models.schemas import (
    UserCreate,
    UserResponse,
    UserListResponse,
    RateLimitUpdate,
    RateLimitResponse,
    UsageSummary,
    UsageResponse,
    ModelUsage,
    ModelPricingCreate,
    ModelPricingResponse,
    ModelPricingListResponse,
    PricingHistoryEntry,
    PricingHistoryResponse,
)
from ..middleware.auth import verify_admin_key
from ..database import (
    create_user,
    get_user_by_id,
    get_all_users,
    delete_user,
    delete_all_users,
    get_rate_limits,
    update_rate_limits,
    get_usage_stats,
    set_model_pricing,
    get_model_pricing,
    get_all_model_pricing,
    delete_model_pricing,
    get_pricing_history,
)

router = APIRouter(prefix="/admin", tags=["admin"])

ALLOWED_MODELS = ["llama3.2:1b", "moondream"]


@router.post("/users", response_model=UserResponse)
async def create_new_user(
    user_data: UserCreate,
    _admin: bool = Depends(verify_admin_key),
):
    """Create a new user with an API key."""
    # Check if user already exists
    existing = await get_user_by_id(user_data.user_id)
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    try:
        user_id, api_key = await create_user(user_data.user_id)
        user = await get_user_by_id(user_id)
        return UserResponse(
            user_id=user_id,
            api_key=api_key,
            created_at=user["created_at"] if user else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users", response_model=UserListResponse)
async def list_users(
    _admin: bool = Depends(verify_admin_key),
):
    """List all users."""
    users = await get_all_users()
    return UserListResponse(
        users=[
            UserResponse(
                user_id=u["id"],
                api_key=u["api_key"],
                created_at=u["created_at"],
            )
            for u in users
        ]
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    _admin: bool = Depends(verify_admin_key),
):
    """Get a specific user."""
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        user_id=user["id"],
        api_key=user["api_key"],
        created_at=user["created_at"],
    )


@router.delete("/users")
async def remove_all_users(
    _admin: bool = Depends(verify_admin_key),
):
    """Delete all users, their rate limits, and usage records."""
    count = await delete_all_users()
    return {"message": f"Deleted {count} users and all associated data"}


@router.delete("/users/{user_id}")
async def remove_user(
    user_id: str,
    _admin: bool = Depends(verify_admin_key),
):
    """Delete a user (revoke access)."""
    success = await delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": f"User {user_id} deleted successfully"}


@router.get("/users/{user_id}/usage", response_model=UsageSummary)
async def get_user_usage(
    user_id: str,
    _admin: bool = Depends(verify_admin_key),
):
    """Get usage statistics for a specific user."""
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    stats = await get_usage_stats(user_id)
    limits = await get_rate_limits(user_id)

    return UsageSummary(
        user_id=user_id,
        usage=UsageResponse(
            total_tokens=stats["total_tokens"],
            prompt_tokens=stats["prompt_tokens"],
            completion_tokens=stats["completion_tokens"],
            total_cost=stats["total_cost"],
            request_count=stats["request_count"],
            by_model={
                model: ModelUsage(**data)
                for model, data in stats["by_model"].items()
            },
        ),
        rate_limits=RateLimitResponse(user_id=user_id, **limits) if limits else None,
    )


@router.get("/users/{user_id}/limits", response_model=RateLimitResponse)
async def get_user_limits(
    user_id: str,
    _admin: bool = Depends(verify_admin_key),
):
    """Get rate limits for a specific user."""
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    limits = await get_rate_limits(user_id)
    if not limits:
        raise HTTPException(status_code=404, detail="Rate limits not found")

    return RateLimitResponse(user_id=user_id, **limits)


@router.put("/users/{user_id}/limits", response_model=RateLimitResponse)
async def set_user_limits(
    user_id: str,
    limits: RateLimitUpdate,
    _admin: bool = Depends(verify_admin_key),
):
    """Update rate limits for a specific user."""
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update only provided fields
    update_data = limits.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    success = await update_rate_limits(user_id, **update_data)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update rate limits")

    # Return updated limits
    updated = await get_rate_limits(user_id)
    return RateLimitResponse(user_id=user_id, **updated)


# Pricing endpoints
@router.post("/pricing", response_model=ModelPricingResponse, status_code=201)
async def create_model_pricing(
    pricing: ModelPricingCreate,
    _admin: bool = Depends(verify_admin_key),
):
    """Set pricing for a model."""
    if pricing.model not in ALLOWED_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Model must be one of: {', '.join(ALLOWED_MODELS)}",
        )
    try:
        await set_model_pricing(
            model=pricing.model,
            input_cost_per_million=pricing.input_cost_per_million,
            output_cost_per_million=pricing.output_cost_per_million,
        )

        # Fetch and return the created/updated pricing
        result = await get_model_pricing(pricing.model)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to retrieve pricing after creation")

        return ModelPricingResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pricing", response_model=ModelPricingListResponse)
async def list_model_pricing(
    _admin: bool = Depends(verify_admin_key),
):
    """List all model pricing."""
    pricing_list = await get_all_model_pricing()
    return ModelPricingListResponse(
        pricing=[ModelPricingResponse(**p) for p in pricing_list]
    )


@router.get("/pricing/{model}", response_model=ModelPricingResponse)
async def get_pricing_for_model(
    model: str,
    _admin: bool = Depends(verify_admin_key),
):
    """Get pricing for a specific model."""
    pricing = await get_model_pricing(model)
    if not pricing:
        raise HTTPException(status_code=404, detail=f"Pricing not found for model: {model}")

    return ModelPricingResponse(**pricing)


@router.put("/pricing/{model}", response_model=ModelPricingResponse)
async def update_model_pricing(
    model: str,
    pricing: ModelPricingCreate,
    _admin: bool = Depends(verify_admin_key),
):
    """Update pricing for a specific model."""
    # Check if pricing exists
    existing = await get_model_pricing(model)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Pricing not found for model: {model}")

    # Update pricing
    try:
        await set_model_pricing(
            model=model,
            input_cost_per_million=pricing.input_cost_per_million,
            output_cost_per_million=pricing.output_cost_per_million,
        )

        # Fetch and return the updated pricing
        result = await get_model_pricing(model)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to retrieve pricing after update")

        return ModelPricingResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pricing/{model}")
async def remove_model_pricing(
    model: str,
    _admin: bool = Depends(verify_admin_key),
):
    """Delete pricing for a model."""
    success = await delete_model_pricing(model)
    if not success:
        raise HTTPException(status_code=404, detail=f"Pricing not found for model: {model}")

    return {"message": f"Pricing for model {model} deleted successfully"}


@router.get("/pricing/history/all", response_model=PricingHistoryResponse)
async def get_all_pricing_history(
    _admin: bool = Depends(verify_admin_key),
):
    """Get pricing change history for all models."""
    history = await get_pricing_history()
    return PricingHistoryResponse(
        history=[PricingHistoryEntry(**h) for h in history]
    )


@router.get("/pricing/history/{model}", response_model=PricingHistoryResponse)
async def get_model_pricing_history(
    model: str,
    _admin: bool = Depends(verify_admin_key),
):
    """Get pricing change history for a specific model."""
    history = await get_pricing_history(model)
    return PricingHistoryResponse(
        history=[PricingHistoryEntry(**h) for h in history]
    )
