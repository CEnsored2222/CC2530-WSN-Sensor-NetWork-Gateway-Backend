# -*- coding: utf-8 -*-
"""网关权限检查工具函数。

使用 user_gateways 中间表判断用户是否已绑定指定网关。
"""
from extensions import db
from models.user_gateway import UserGateway


def check_user_bound_to_gateway(user_id, gateway_id):
    """检查用户是否已绑定指定网关。

    Args:
        user_id: 用户 ID
        gateway_id: 网关 ID

    Returns:
        bool: 是否已绑定
    """
    return db.session.query(
        UserGateway.query.filter_by(
            user_id=user_id, gateway_id=gateway_id
        ).exists()
    ).scalar()


def get_user_gateway_ids(user_id):
    """获取用户绑定的所有网关 ID 列表。

    Args:
        user_id: 用户 ID

    Returns:
        list[int]: 网关 ID 列表
    """
    ugs = UserGateway.query.filter_by(user_id=user_id).all()
    return [ug.gateway_id for ug in ugs]


def get_bound_user_ids(gateway_id):
    """获取绑定了指定网关的所有用户 ID 列表。

    Args:
        gateway_id: 网关 ID

    Returns:
        list[int]: 用户 ID 列表
    """
    ugs = UserGateway.query.filter_by(gateway_id=gateway_id).all()
    return [ug.user_id for ug in ugs]
