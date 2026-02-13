from fastapi import APIRouter, Depends

from ..models.schemas import UsageResponse, ModelUsage
from ..middleware.auth import get_current_user
from ..services.token_tracker import token_tracker
from ..database import get_all_model_pricing

router = APIRouter(prefix="/v1", tags=["usage"])


@router.get("/usage")
async def get_my_usage(
    current_user: dict = Depends(get_current_user),
):
    """Get the current user's token usage statistics."""
    user_id = current_user["id"]
    stats = await token_tracker.get_user_usage(user_id)

    response = UsageResponse(
        total_tokens=stats["total_tokens"],
        prompt_tokens=stats["prompt_tokens"],
        completion_tokens=stats["completion_tokens"],
        total_cost=stats["total_cost"],
        request_count=stats["request_count"],
        by_model={
            model: ModelUsage(**data)
            for model, data in stats["by_model"].items()
        },
    )
    result = response.model_dump()
    result["user_id"] = user_id
    return result


@router.get("/usage/summary")
async def get_usage_summary(
    current_user: dict = Depends(get_current_user),
):
    """Get a summary of the current user's usage by model."""
    user_id = current_user["id"]
    stats = await token_tracker.get_user_usage(user_id)

    return {
        "user_id": user_id,
        "total_tokens": stats["total_tokens"],
        "total_cost": stats["total_cost"],
        "by_model": stats["by_model"],
    }


@router.get("/pricing")
async def get_pricing(current_user: dict = Depends(get_current_user)):
    """Get current model pricing (read-only for users)."""
    pricing = await get_all_model_pricing()
    return {"pricing": [dict(p) if not isinstance(p, dict) else p for p in pricing]}
