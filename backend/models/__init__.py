# -*- coding: utf-8 -*-
"""导入所有模型,确保 db.create_all() 时建表。"""
from models.user import User
from models.gateway import Gateway
from models.device import Device
from models.sensor_data import SensorData
from models.subscription import Subscription
from models.operation_log import OperationLog

__all__ = ["User", "Gateway", "Device", "SensorData", "Subscription", "OperationLog"]
