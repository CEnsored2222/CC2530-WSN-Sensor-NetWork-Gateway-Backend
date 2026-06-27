# -*- coding: utf-8 -*-
"""MLP 微调调度器。

daemon 线程每 MLP_SCHEDULER_CHECK_INTERVAL 秒检查环形缓冲区新数据量,
满足条件则 spawn 子线程执行微调(与 DataBuffer._flush_loop 同模式)。
全局锁保证同时最多 1 个微调运行(自动/手动互斥)。

微调完成后立即在同一子线程内触发评估(使用缓存的 eval_set),
        不依赖 API 触发,不检查新数据量。
通过 import extensions 模块访问 data_buffer(非 app.extensions dict)。
微调失败时指数退避(120s/240s/.../1920s),避免持续失败刷屏。
Python 端过滤设备类型,避免 SQLAlchemy JSON contains 误匹配。
"""
import threading
import time
import traceback
from datetime import datetime

from config import Config
from extensions import db
from models.device import Device
from models.ml import MlModel


class FineTuneScheduler:
    def __init__(self, app, onnx_trainer, check_interval=None):
        self._app = app
        self._trainer = onnx_trainer
        self._check_interval = check_interval or Config.MLP_SCHEDULER_CHECK_INTERVAL
        self._running = False
        self._thread = None
        self._finetune_lock = threading.Lock()        # 全局锁:所有微调串行化
        self._last_finetune = {}                       # {model_type: timestamp}
        self._finetuning = set()                       # 正在微调的 model_type
        self._finetune_active = False                  # 全局标志:任一微调进行中
        # 缓存微调时的 eval_set(后 20% 留出集),供评估直接使用
        self._eval_set = {}                             # {model_type: [(ts, did, fields), ...]}
        # 微调失败计数器,用于指数退避
        self._fail_count = {}                          # {model_type: 连续失败次数}

    def _schedule_loop(self):
        while self._running:
            time.sleep(self._check_interval)
            try:
                with self._app.app_context():
                    self._check_and_finetune()
            except Exception:
                traceback.print_exc()

    def _check_and_finetune(self):
        # 全局互斥:同时最多 1 个微调在运行
        with self._finetune_lock:
            if self._finetune_active:
                return
            for model_type in ("mlp_temp_hum", "mlp_light"):
                if model_type in self._finetuning:
                    continue
                ml_model = MlModel.query.get(model_type)
                if not ml_model or not ml_model.last_train_time:
                    continue
                # 通过 import extensions 模块访问 data_buffer
                import extensions as ext_mod
                data_buf = getattr(ext_mod, "data_buffer", None)
                if data_buf is None:
                    continue
                ring_buf = data_buf.ring_buffer
                if ring_buf is None:
                    continue
                # 从环形缓冲区查新数据数量(而非 DB,避免 600s flush 延迟)
                device_ids = self._get_device_ids(model_type)
                new_data = ring_buf.get_aggregated_since(
                    device_ids, ml_model.last_train_time.timestamp()
                )
                new_count = len(new_data)
                last_ft = self._last_finetune.get(model_type, 0)
                interval = time.time() - last_ft
                if (new_count >= Config.MLP_FINETUNE_MIN_SAMPLES
                        and interval >= Config.MLP_FINETUNE_INTERVAL):
                    self._finetuning.add(model_type)
                    self._finetune_active = True
                    # 只传 model_type 字符串,子线程内重新查询
                    threading.Thread(
                        target=self._run_finetune,
                        args=(model_type,),
                        daemon=True,
                        name=f"finetune-{model_type}"
                    ).start()
                    break  # 每周期最多启动 1 个微调

    def _get_device_ids(self, model_type):
        """按 model_type 查询所有同类型设备 id(device.type 是 JSON 数组)。

        Python 端过滤,避免 SQLAlchemy JSON contains 误匹配。
        """
        if model_type == "mlp_temp_hum":
            required = ("temperature", "humidity")
        else:
            required = ("light",)
        all_devices = Device.query.all()
        result = []
        for d in all_devices:
            if d.type and any(t in d.type for t in required):
                result.append(d.id)
        return result

    def manual_finetune(self, model_type):
        """手动微调(API 调用),同样受全局锁保护。

        Returns:
            (success: bool, message: str)
        """
        with self._finetune_lock:
            if self._finetune_active:
                return False, "已有模型正在微调中,请稍后重试"
            if model_type in self._finetuning:
                return False, f"{model_type} 正在微调中"
            ml_model = MlModel.query.get(model_type)
            if not ml_model or not ml_model.last_train_time:
                return False, "模型未预训练,请先 POST /mlp/train"
            self._finetuning.add(model_type)
            self._finetune_active = True
            threading.Thread(
                target=self._run_finetune,
                args=(model_type,),
                daemon=True,
                name=f"finetune-manual-{model_type}"
            ).start()
            return True, "微调已启动"

    def _run_finetune(self, model_type):
        """子线程入口:在自己的 app_context 内重新查询 ml_model。

        微调完成后立即在同一子线程内调用评估(使用缓存的 eval_set)。
        异常时指数退避(失败计数器 + 2^N 倍退避)。
        """
        try:
            with self._app.app_context():
                ml_model = MlModel.query.get(model_type)
                if not ml_model:
                    return
                trainer = self._trainer
                # 微调时缓存 eval_set 到 self._eval_set[model_type]
                result = trainer.fine_tune(model_type, ml_model,
                                           eval_set_cache=self._eval_set)
                if "error" in result:
                    print(f"[MLP] 微调失败 {model_type}: {result['error']}")
                    # 微调数据不足等非异常情况,不计入失败退避
                    self._last_finetune[model_type] = time.time()
                    return
                # 微调成功后更新 DB 的 last_finetune_time
                ml_model.last_finetune_time = datetime.now()
                db.session.commit()
                self._last_finetune[model_type] = time.time()
                self._fail_count[model_type] = 0
                # 微调完成后立即自动触发评估(同一子线程)
                try:
                    trainer.evaluate(model_type,
                                     eval_set=self._eval_set.get(model_type))
                except Exception:
                    traceback.print_exc()  # 评估失败不影响微调结果
        except Exception:
            traceback.print_exc()
            # 微调失败,指数退避
            self._fail_count[model_type] = self._fail_count.get(model_type, 0) + 1
            backoff = self._check_interval * (2 ** min(self._fail_count[model_type], 5))
            self._last_finetune[model_type] = time.time() + backoff - self._check_interval
        finally:
            with self._finetune_lock:
                self._finetuning.discard(model_type)
                self._finetune_active = False

    def start(self):
        # 从 ml_models.last_finetune_time 恢复(而非 updated_at)
        with self._app.app_context():
            for mt in ("mlp_temp_hum", "mlp_light"):
                m = MlModel.query.get(mt)
                if m and m.last_finetune_time:
                    self._last_finetune[mt] = m.last_finetune_time.timestamp()
                else:
                    self._last_finetune[mt] = 0
        self._running = True
        self._thread = threading.Thread(target=self._schedule_loop,
                                        daemon=True, name="mlp-scheduler")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
