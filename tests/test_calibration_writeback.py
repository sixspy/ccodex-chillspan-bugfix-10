"""校准登记回写探头主档：三份失败夹具（甲路径 / 乙路径 / 争用）。

修补前应全部为红：
- 甲：登记回执成功但 probes.calibration_due 仍为旧值（到期视图仍临期）。
- 乙：影子登记未转正却已受理，主档到期未与登记同源（混用）。
- 争用：两值班窗同探头抢登记，后到未抢锁也未仅存痕。
"""

from fastapi.testclient import TestClient

from app import app
from db import connect, init_db


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "t.db")
    init_db()


def _auth(c: TestClient, user: str = "admin") -> dict:
    tok = c.post(
        "/api/login", json={"username": user, "password": "123456"}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def _probe(c: TestClient, h: dict, code: str) -> dict:
    rows = c.get("/api/probes", headers=h).json()["items"]
    return next(p for p in rows if p["probe_code"] == code)


def test_jia_registration_and_due_refresh_are_one_transaction(tmp_path, monkeypatch):
    """甲路径：登记正式落库则主档到期同事务零改刷新，否则整笔回滚。"""
    _db(tmp_path, monkeypatch)
    c = TestClient(app)
    h = _auth(c)

    # 到期视图（仪表盘）：种子中 PR-HD-A2 / PR-HB-B1 / PR-HB-B2 / PR-XN-D1 已过期，共 4
    dash_before = c.get("/api/dashboard", headers=h).json()
    assert dash_before["calibration_overdue"] == 4

    # PR-HN-C1：到期 2027-02-01，挂批 TB-CK-HN-03-001，仓间 CK-HN-03
    probe = _probe(c, h, "PR-HN-C1")
    old_due = probe["calibration_due"]
    new_due = "2028-09-30"
    r = c.post(
        "/api/calibrations",
        headers=h,
        json={
            "probe_id": probe["id"],
            "offset_c": 0.2,
            "valid_until": new_due,
            "officer": "张工",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["probe_due_synced"] is True
    assert body["calibration_due"] == new_due

    # 到期视图：探头列表
    assert _probe(c, h, "PR-HN-C1")["calibration_due"] == new_due

    # 登记视图：探头详情 + 校准记录
    detail = c.get(f"/api/probes/{probe['id']}", headers=h).json()
    assert detail["probe"]["calibration_due"] == new_due
    assert detail["calibrations"][0]["valid_until"] == new_due
    cals = c.get(
        f"/api/calibrations?probe_id={probe['id']}", headers=h
    ).json()["items"]
    assert cals[0]["valid_until"] == new_due
    assert cals[0]["probe_calibration_due"] == new_due
    assert cals[0]["due_in_sync"] is True

    # 挂批视图：批次行挂接探头到期
    batches = c.get("/api/batches", headers=h).json()["items"]
    batch = next(b for b in batches if b["probe_id"] == probe["id"])
    assert batch["probe_calibration_due"] == new_due

    # 互证视图：批次互证挂同一到期
    proof = c.get(
        f"/api/proof/batch/{batch['batch_code']}", headers=h
    ).json()
    assert proof["probe_calibration_due"] == new_due

    # 占用视图：仓间占用明细挂同一到期
    chamber = c.get("/api/chambers/3", headers=h).json()
    occupied = next(p for p in chamber["probes"] if p["id"] == probe["id"])
    assert occupied["calibration_due"] == new_due

    # 到期视图（仪表盘）随主档同源刷新：PR-HB-B1 仍在期，故临期数不变
    dash_after = c.get("/api/dashboard", headers=h).json()
    assert dash_after["calibration_overdue"] == 4

    # 另将已过期探头 PR-HD-A2 转正式校准后，临期数应减一
    pr_a2 = _probe(c, h, "PR-HD-A2")
    r_a2 = c.post(
        "/api/calibrations",
        headers=h,
        json={
            "probe_id": pr_a2["id"],
            "offset_c": 0.1,
            "valid_until": "2028-02-01",
            "officer": "张工",
        },
    )
    assert r_a2.status_code == 200, r_a2.text
    dash_refreshed = c.get("/api/dashboard", headers=h).json()
    assert dash_refreshed["calibration_overdue"] == 3

    # 对账汇总：校准到期指标随主档同源
    recon = c.get("/api/reconcile", headers=h).json()
    assert recon["summary"]["calibration_overdue"] == 3

    # 回写审计须如实，不得假绿
    audit = c.get("/api/audit?limit=50", headers=h).json()["items"]
    ev = next(
        x
        for x in audit
        if x["action"] == "calibration_add" and x["target"] == "PR-HN-C1"
    )
    assert ev["payload"]["probe_due_synced"] is True
    assert ev["payload"]["previous_due"] == old_due
    assert ev["payload"]["calibration_due"] == new_due

    # 主档回写失败 => 登记整笔回滚（无登记条、到期零改、无成功审计）
    probe2 = _probe(c, h, "PR-HD-A2")
    old_due2 = probe2["calibration_due"]
    rollback_due = "2029-01-01"

    def _boom(conn, probe_id, valid_until):
        raise RuntimeError("注入：探头主档到期回写失败")

    monkeypatch.setattr(
        "probes_svc.sync_calibration_due", _boom, raising=False
    )
    strict = TestClient(app, raise_server_exceptions=False)
    r2 = strict.post(
        "/api/calibrations",
        headers=h,
        json={
            "probe_id": probe2["id"],
            "offset_c": 0.0,
            "valid_until": rollback_due,
            "officer": "张工",
        },
    )
    assert r2.status_code >= 500, r2.text
    assert _probe(strict, h, "PR-HD-A2")["calibration_due"] == old_due2
    with connect() as conn:
        left = conn.execute(
            "SELECT COUNT(*) c FROM calibration_records WHERE probe_id=? AND valid_until=?",
            (probe2["id"], rollback_due),
        ).fetchone()["c"]
        assert left == 0
        synced = conn.execute(
            """SELECT COUNT(*) c FROM audit_trail
               WHERE action='calibration_add' AND target='PR-HD-A2'
                 AND payload LIKE ?""",
            (f"%{rollback_due}%",),
        ).fetchone()["c"]
        assert synced == 0


def test_yi_shadow_registration_is_refused_and_due_never_mixed(tmp_path, monkeypatch):
    """乙路径禁用：影子登记未转正不得刷新到期；偏离纪要应记偏航并拒写。"""
    _db(tmp_path, monkeypatch)
    c = TestClient(app)
    h = _auth(c)

    # PR-HN-C2：到期 2027-03-15
    probe = _probe(c, h, "PR-HN-C2")
    old_due = probe["calibration_due"]
    shadow_due = "2029-05-01"
    r = c.post(
        "/api/calibrations",
        headers=h,
        json={
            "probe_id": probe["id"],
            "offset_c": 0.0,
            "valid_until": shadow_due,
            "officer": "复核员",
            "mode": "影子",
        },
    )
    assert r.status_code == 422, r.text

    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM calibration_records WHERE probe_id=? AND valid_until=?",
            (probe["id"], shadow_due),
        ).fetchall()
        assert rows == [], "影子登记条未转正，不得落库"
        due = conn.execute(
            "SELECT calibration_due FROM probes WHERE id=?", (probe["id"],)
        ).fetchone()["calibration_due"]
        assert due == old_due, "影子登记未转正，主档到期必须零改"
        dev = conn.execute(
            """SELECT * FROM audit_trail
               WHERE action='calibration_writeback_deviation'
               ORDER BY id DESC"""
        ).fetchone()
        assert dev is not None, "偏离纪要须记登记回写偏航"
        assert dev["target"] == "PR-HN-C2"

    # 正式路径仍须同源转正，且库内不得留下待复核影子条
    formal_due = "2028-06-30"
    r2 = c.post(
        "/api/calibrations",
        headers=h,
        json={
            "probe_id": probe["id"],
            "offset_c": 0.0,
            "valid_until": formal_due,
            "officer": "张工",
            "mode": "正式",
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["calibration_due"] == formal_due
    with connect() as conn:
        due = conn.execute(
            "SELECT calibration_due FROM probes WHERE id=?", (probe["id"],)
        ).fetchone()["calibration_due"]
        assert due == formal_due
        pending = conn.execute(
            """SELECT COUNT(*) c FROM calibration_records
               WHERE probe_id=? AND status!='有效'""",
            (probe["id"],),
        ).fetchone()["c"]
        assert pending == 0, "单轨正式路径不得留存影子/待复核条"


def test_bing_two_duty_windows_same_probe_contend_for_probe_lock(tmp_path, monkeypatch):
    """两值班窗同探头抢登记：后到争用仅存痕，业务零写。"""
    _db(tmp_path, monkeypatch)
    c = TestClient(app)
    h_admin = _auth(c, "admin")  # 值班窗甲
    h_ops = _auth(c, "ops")  # 值班窗乙

    probe = _probe(c, h_admin, "PR-XN-D1")
    old_due = probe["calibration_due"]
    lock_key = f"probe:{probe['id']}"
    new_due = "2028-12-31"

    assert (
        c.post(
            "/api/locks/acquire", headers=h_admin, json={"lock_key": lock_key}
        ).status_code
        == 200
    )

    r = c.post(
        "/api/calibrations",
        headers=h_ops,
        json={
            "probe_id": probe["id"],
            "offset_c": 0.0,
            "valid_until": new_due,
            "officer": "值班员乙",
        },
    )
    assert r.status_code == 409, r.text

    # 后到仅存痕
    cont = c.get("/api/contention", headers=h_admin).json()["items"]
    assert any(
        x["lock_key"] == lock_key
        and x["actor"] == "ops"
        and x["action"] == "争用"
        for x in cont
    ), "后到争用须在 contention_log 留痕"

    # 业务零写：到期与登记条均不变
    assert _probe(c, h_admin, "PR-XN-D1")["calibration_due"] == old_due
    with connect() as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) c FROM calibration_records WHERE probe_id=?",
                (probe["id"],),
            ).fetchone()["c"]
            == 0
        )

    # 锁释放后，同一探头可正式登记并同源回写
    assert (
        c.post(
            "/api/locks/release", headers=h_admin, json={"lock_key": lock_key}
        ).status_code
        == 200
    )
    r2 = c.post(
        "/api/calibrations",
        headers=h_ops,
        json={
            "probe_id": probe["id"],
            "offset_c": 0.0,
            "valid_until": new_due,
            "officer": "值班员乙",
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["calibration_due"] == new_due
    assert _probe(c, h_admin, "PR-XN-D1")["calibration_due"] == new_due
