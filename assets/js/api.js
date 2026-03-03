/**
 * 立米AI Ryu兵衛 - API通信用ユーティリティ
 */

const API_BASE_URL = "https://ryubee-api.onrender.com/v1";

const api = {
  /**
   * 案件一覧を取得する
   */
  async getJobs() {
    try {
      const res = await fetch(`${API_BASE_URL}/jobs`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.error("案件一覧の取得に失敗しました", err);
      throw err;
    }
  },

  /**
   * 案件詳細を取得する
   * @param {string} jobId 
   */
  async getJobDetail(jobId) {
    try {
      const res = await fetch(`${API_BASE_URL}/jobs/${jobId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.error("案件詳細の取得に失敗しました", err);
      throw err;
    }
  },

  /**
   * 案件を保存（更新）する
   * @param {string} jobId 
   * @param {Object} payload 
   */
  async saveJob(jobId, payload) {
    try {
      const res = await fetch(`${API_BASE_URL}/jobs/${jobId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.error("案件の保存に失敗しました", err);
      throw err;
    }
  },

  /**
   * 画像を送信して立米を見積もる
   * @param {FormData} formData
   */
  async estimateVolume(formData) {
    try {
      const res = await fetch(`${API_BASE_URL}/volume-estimate`, {
        method: "POST",
        body: formData, // fetchはFormDataを渡すと自動でmultipart/form-dataヘッダを設定する
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.error("立米計算APIの呼び出しに失敗しました", err);
      throw err;
    }
  },

  /**
   * 作業書PDFのURLを生成する
   * @param {string} jobId 
   */
  getWorksheetUrl(jobId) {
    return `${API_BASE_URL}/jobs/${jobId}/worksheet`;
  }
};
