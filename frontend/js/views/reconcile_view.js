export const reconcileViewTemplate = `
<section class="panel">
  <h2>仓间对账互证</h2>
  <div class="form-row">
    <div><label>仓间编码</label><input v-model="reconCode"/></div>
    <div><label>批次互证编码</label><input v-model="proofCode"/></div>
  </div>
  <div class="actions">
    <button @click="loadRecon">对账单仓</button>
    <button class="secondary" @click="loadProof">批次互证</button>
    <button class="secondary" @click="loadReconAll">全仓对账</button>
  </div>
  <div v-if="reconOne" class="detail-box">
    <p>配额 {{ reconOne.quota_batches }} · 在批 {{ reconOne.active_batches }} · <span :class="reconOne.balanced ? 'ok' : 'bad'">{{ reconOne.balanced ? "平衡" : "失衡" }}</span></p>
  </div>
  <div v-if="proofOne" class="detail-box">
    <p>状态 {{ proofOne.status }} · 开放游标 {{ proofOne.open_excursions }} · 温谱 {{ proofOne.spectrum_exports }} · 探头到期 {{ proofOne.probe_calibration_due }}</p>
  </div>
  <div v-if="reconSummary" class="detail-box">
    <p>仓间 {{ reconSummary.total }} · 平衡 {{ reconSummary.balanced }} · 失衡 {{ reconSummary.unbalanced }} · 校准临期 {{ reconSummary.calibration_overdue }}</p>
  </div>
  <table class="data-table">
    <thead><tr><th>仓间</th><th>区域</th><th>在批</th><th>余配额</th><th>平衡</th></tr></thead>
    <tbody>
      <tr v-for="r in reconAllItems" :key="r.chamber_code">
        <td>{{ r.chamber_code }}</td>
        <td>{{ r.region }}</td>
        <td>{{ r.active_batches }}</td>
        <td>{{ r.quota_left }}</td>
        <td>{{ r.balanced ? "是" : "否" }}</td>
      </tr>
    </tbody>
  </table>
</section>
`;