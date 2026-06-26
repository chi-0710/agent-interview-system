"""统一用户上下文依赖

当前阶段为单用户模式，所有请求默认返回 default_user。
未来接入认证后，只需修改 get_current_user 即可让全系统切换到真实用户。
"""
from dataclasses import dataclass

from fastapi import Header


@dataclass
class CurrentUser:
    """当前请求的用户上下文"""
    user_id: str
    display_name: str = "默认用户"


async def get_current_user(
    x_user_id: str | None = Header(default=None),
) -> CurrentUser:
    """
    获取当前用户。

    优先从 X-User-ID 请求头读取（前端可传入），否则使用 default_user。
    未来接入 JWT/OAuth 时，这里改为解析 token 并返回真实用户。
    """
    if x_user_id:
        return CurrentUser(user_id=x_user_id, display_name=x_user_id)
    return CurrentUser(user_id="default_user", display_name="默认用户")
