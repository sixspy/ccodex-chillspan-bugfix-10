# 校准登记回写纪要（当日封口）

- 封口日期：2026-11-23
- 范围：校准服务写回链、探头服务主档、批次挂接、对账汇总、仓间占用、校准页与探头页
- 单库：仅 `data/app.db`，不动多库

## 口径

校准登记与探头到期须**同事务单轨**，两边不得混用：

- **甲路径（采用）**：登记正式落库时，`probes.calibration_due` 于同一事务内
  **零改**刷新为登记 `valid_until`（不做任何推导）；任一步失败则登记整笔回滚
  （登记条、审计、主档到期三者同生共死）。
- **乙路径（未采用）**：允许先落影子登记条、正式到期零改、待复核后原子晋升。
  本次不启用该轨；任何影子/待复核模式一律视为偏离纪要，记
  `calibration_writeback_deviation`（登记回写偏航）并拒写。
- **折中禁用**：不得只刷新登记页、只改勾图标，或让登记新日期与主档到期分叉。
  混轨会表现为「登记新日期仍临期」。

## 并发

- 同一探头并发登记须抢 `probe:<id>` 锁；后到争用只写 `contention_log` 争用痕，
  业务零写，返回 409。锁释放后方可正式登记。

## 同源五面

到期值只认探头主档 `calibration_due`，下列五处同源读取，不得各自推导：

1. 到期视图：`GET /api/probes`、`GET /api/probes/{id}`、`/api/dashboard`
2. 登记视图：`GET /api/calibrations`（`probe_calibration_due`、`due_in_sync`）
3. 挂批视图：`GET /api/batches`（`probe_calibration_due`）
4. 互证视图：`GET /api/proof/batch/{batch_code}`（`probe_calibration_due`）
5. 占用视图：`GET /api/chambers/{id}`（`probes[].calibration_due`）

## 验收

- 三份失败夹具先红后绿：`tests/test_calibration_writeback.py`
  （甲：到期未刷新；乙：影子未转正却已刷到期；争用：两值班窗同探头抢登记）。
- 到期日五面一致；本机夹具可跑。
