"""
黑白名单 过滤规则 API
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, FilterRule
from app.schemas import (
    FilterRuleCreate, FilterRuleUpdate, FilterRuleInfo,
    ResponseModel, PageResult,
)
from app.api.deps import get_current_user, get_page_params, paginate_query, make_page_result

router = APIRouter(tags=["黑白名单规则"])


@router.get("/filter/rules", response_model=ResponseModel[PageResult[FilterRuleInfo]])
def list_rules(
    rule_type: Optional[str] = None,
    is_enabled: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    pp=Depends(get_page_params),
):
    page, page_size = pp
    q = db.query(FilterRule).filter(FilterRule.user_id == user.id)
    if rule_type:
        q = q.filter(FilterRule.rule_type == rule_type)
    if is_enabled is not None:
        q = q.filter(FilterRule.is_enabled == is_enabled)
    q = q.order_by(FilterRule.priority.desc(), FilterRule.id.desc())
    items, total, _ = paginate_query(q, db, page, page_size)
    return ResponseModel.success(data=make_page_result(items, total, page, page_size))


@router.post("/filter/rule", response_model=ResponseModel[FilterRuleInfo])
def create_rule(data: FilterRuleCreate, user=Depends(get_current_user), db=Depends(get_db)):
    data.user_id = user.id
    obj = FilterRule(**data.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return ResponseModel.success(data=obj, message="创建成功")


@router.put("/filter/rule/{rid}", response_model=ResponseModel[FilterRuleInfo])
def update_rule(rid: int, data: FilterRuleUpdate, user=Depends(get_current_user), db=Depends(get_db)):
    obj = db.query(FilterRule).filter(FilterRule.id == rid, FilterRule.user_id == user.id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "规则不存在")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return ResponseModel.success(data=obj, message="更新成功")


@router.delete("/filter/rule/{rid}")
def delete_rule(rid: int, user=Depends(get_current_user), db=Depends(get_db)):
    obj = db.query(FilterRule).filter(FilterRule.id == rid, FilterRule.user_id == user.id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "规则不存在")
    db.delete(obj); db.commit()
    return ResponseModel.success(message="删除成功")


@router.post("/filter/rule/{rid}/toggle")
def toggle_rule(rid: int, data: dict, user=Depends(get_current_user), db=Depends(get_db)):
    obj = db.query(FilterRule).filter(FilterRule.id == rid, FilterRule.user_id == user.id).first()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "规则不存在")
    obj.is_enabled = 1 if data.get("enabled", True) else 0
    db.commit()
    return ResponseModel.success(message="已更新")
