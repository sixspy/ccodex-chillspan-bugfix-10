"""探头校准记录。

登记回写纪要（当日封口）：
- 单轨：校准登记与探头到期日同事务落库，两边不得混用；
  仅存在一条正式路径——登记正式落库则 `probes.calibration_due` 同事务
  零改刷新（原值直取 `valid_until`，不做任何推导），否则登记整笔回滚。
- 禁用影子登记 / 待复核后原子晋升等折中轨；混轨会出现「登记新日期仍临期」。
- 同一探头并发登记须抢 `probe:<id>` 锁，后到争用只记争用痕、业务零写。
- 偏离纪要即记 `calibration_writeback_deviation`（登记回写偏航）并拒写。
"""
from __future__ import annotations

import probes_svc
from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user, require_writer
from db import connect, now_iso, write_audit
from locks import release, try_acquire
from models import CalibrationIn

router = APIRouter(tags=["calibration"])


@router.get("/api/calibrations")
def list_calibrations(authorization: AuthHeader = None, probe_id: int | None = None):
    require_user(authorization)
    with connect() as conn:
        base = """SELECT c.*, p.probe_code,
                         p.calibration_due AS probe_calibration_due
                  FROM calibration_records c
                  JOIN probes p ON p.id=c.probe_id"""
        if probe_id:
            rows = conn.execute(
                base + " WHERE c.probe_id=? ORDER BY c.id DESC",
                (probe_id,),
            ).fetchall()
        else:
            rows = conn.execute(base + " ORDER BY c.id DESC").fetchall()
        items = []
        for r in rows:
            d = dict(r)
            # 登记视图与到期视图同源：最新登记须与主档到期零差
            d["due_in_sync"] = d["valid_until"] == d["probe_calibration_due"]
            items.append(d)
        return {"items": items}


@router.post("/api/calibrations")
def add_calibration(body: CalibrationIn, authorization: AuthHeader = None):
    user = require_writer(authorization)
    lock_key = f"probe:{body.probe_id}"
    with connect() as conn:
        probe = conn.execute(
            "SELECT * FROM probes WHERE id=?", (body.probe_id,)
        ).fetchone()
        if not probe:
            raise HTTPException(404, "探头不存在")

        # 单轨：任何影子/待复核混轨模式一律记偏航并拒写
        if body.mode != "正式":
            write_audit(
                conn,
                user,
                "calibration_writeback_deviation",
                probe["probe_code"],
                {
                    "mode": body.mode,
                    "valid_until": body.valid_until,
                    "refused": True,
                    "reason": "禁用影子/待复核混轨；须走正式单轨同事务回写",
                },
            )
            conn.commit()
            raise HTTPException(
                422, "偏离纪要：登记回写偏航，拒写（禁用影子/待复核混轨）"
            )

        # 抢探头锁：后到争用仅存痕，业务零写
        if not try_acquire(conn, lock_key, user):
            conn.commit()  # 争用痕迹独立落库
            raise HTTPException(409, "争用：后到只记争用，不写业务")

        try:
            cur = conn.execute(
                """INSERT INTO calibration_records(probe_id,calibrated_at,offset_c,
                   valid_until,officer,status) VALUES (?,?,?,?,?,?)""",
                (
                    body.probe_id,
                    now_iso(),
                    body.offset_c,
                    body.valid_until,
                    body.officer,
                    "有效",
                ),
            )
            # 甲路径：同事务零改回写探头主档到期；失败即抛错 -> 整笔回滚
            previous_due, calibration_due = probes_svc.sync_calibration_due(
                conn, body.probe_id, body.valid_until
            )
            write_audit(
                conn,
                user,
                "calibration_add",
                probe["probe_code"],
                {
                    "cal_id": cur.lastrowid,
                    "valid_until": body.valid_until,
                    "previous_due": previous_due,
                    "calibration_due": calibration_due,
                    "probe_due_synced": calibration_due == body.valid_until,
                },
            )
            conn.commit()
            return {
                "id": cur.lastrowid,
                "probe_code": probe["probe_code"],
                "valid_until": body.valid_until,
                "calibration_due": calibration_due,
                "probe_due_synced": True,
            }
        except BaseException:
            # 登记条、审计、主档到期回写同事务整笔回滚
            conn.rollback()
            raise
        finally:
            release(conn, lock_key, user)
            conn.commit()
