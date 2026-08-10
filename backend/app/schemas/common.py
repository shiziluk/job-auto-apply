"""
通用响应Schema
"""
from typing import Optional, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    """统一响应格式"""
    code: int = Field(default=200, description="响应码，200表示成功")
    message: str = Field(default="success", description="响应消息")
    data: Optional[T] = Field(default=None, description="响应数据")

    @classmethod
    def success(cls, data=None, message="操作成功"):
        return cls(code=200, message=message, data=data)

    @classmethod
    def error(cls, message="操作失败", code=400, data=None):
        return cls(code=code, message=message, data=data)


class PageParams(BaseModel):
    """分页查询参数"""
    page: int = Field(default=1, ge=1, description="页码，从1开始")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


class PageResult(BaseModel, Generic[T]):
    """分页响应结果"""
    items: list[T] = Field(description="数据列表")
    total: int = Field(description="总记录数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页数量")
    total_pages: int = Field(description="总页数")
