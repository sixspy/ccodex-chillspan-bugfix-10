export const calibrationViewTemplate = `
<section class="panel">
  <h2>探头校准</h2>
  <p class="hint">登记即与探头主档到期同事务回写；单轨正式登记，禁用影子/待复核混轨。</p>
  <div class="form-row">
    <div><label>探头</label>
      <select v-model.number="calForm.probe_id"><option v-for="p in probes" :key="p.id" :value="p.id">{{ p.probe_code }} · 到期 {{ p.calibration_due }}</option></select>
    </div>
    <div><label>偏移(摄氏)</label><input type="number" step="0.1" v-model.number="calForm.offset_c"/></div>
    <div><label>有效至</label><input type="date" v-model="calForm.valid_until"/></div>
    <div><label>质检员</label><input v-model="calForm.officer"/></div>
    <div><label>登记轨</label>
      <select v-model="calForm.mode">
        <option value="正式">正式（同事务回写到期）</option>
        <option value="影子" disabled>影子（禁用 · 会记偏航拒写）</option>
      </select>
    </div>
  </div>
  <div class="actions"><button @click="addCalibration">写入校准</button></div>
  <table class="data-table">
    <thead><tr><th>探头</th><th>校准时间</th><th>偏移</th><th>有效至</th><th>主档到期</th><th>同源</th><th>状态</th></tr></thead>
    <tbody>
      <tr v-for="c in calibrations" :key="c.id">
        <td>{{ c.probe_code }}</td>
        <td>{{ c.calibrated_at }}</td>
        <td>{{ c.offset_c }}</td>
        <td>{{ c.valid_until }}</td>
        <td>{{ c.probe_calibration_due }}</td>
        <td><span class="badge" :class="c.due_in_sync ? 'pass' : 'fail'">{{ c.due_in_sync ? "一致" : "偏离" }}</span></td>
        <td>{{ c.status }}</td>
      </tr>
    </tbody>
  </table>
</section>
`;
