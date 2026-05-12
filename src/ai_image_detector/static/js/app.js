document.addEventListener('DOMContentLoaded', () => {
  const uploadZone = document.getElementById('upload-zone');
  const fileInput = document.getElementById('file-input');
  const uploadSection = document.getElementById('upload-section');
  const analyzingSection = document.getElementById('analyzing-section');
  const resultSection = document.getElementById('result-section');

  // 拖拽上传
  uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('drag-over');
  });

  uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('drag-over');
  });

  uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length > 0) handleFile(files[0]);
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleFile(e.target.files[0]);
    e.target.value = '';
  });

  async function handleFile(file) {
    if (!file.type.startsWith('image/')) {
      alert('请上传图片文件');
      return;
    }

    // 切换到分析中状态
    uploadSection.style.display = 'none';
    analyzingSection.classList.add('active');
    resultSection.classList.remove('active');
    resultSection.style.display = 'none';

    try {
      const formData = new FormData();
      formData.append('file', file);

      const resp = await fetch('/api/detect', {
        method: 'POST',
        body: formData,
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '检测失败');
      }

      const data = await resp.json();
      renderResult(data, file);
    } catch (err) {
      alert('检测出错: ' + err.message);
      resetUI();
    }
  }

  function renderResult(data, file) {
    analyzingSection.classList.remove('active');
    resultSection.style.display = 'block';
    resultSection.classList.add('active');

    // 判定卡片
    const verdictCard = document.getElementById('verdict-card');
    verdictCard.className = 'verdict-card ' + data.risk_level;

    const icons = { high: '🤖', medium: '⚠️', low: '✅' };
    document.getElementById('verdict-icon').textContent = icons[data.risk_level] || '🔍';
    document.getElementById('verdict-title').textContent = data.verdict;

    const conf = data.confidence;
    document.getElementById('verdict-subtitle').textContent =
      `综合置信度 ${(conf * 100).toFixed(1)}% · 分析耗时 ${data.analysis_time_ms.toFixed(0)}ms`;

    // 置信度条
    const fill = document.getElementById('confidence-fill');
    fill.className = 'confidence-fill ' + data.risk_level;
    setTimeout(() => { fill.style.width = (conf * 100) + '%'; }, 100);
    document.getElementById('confidence-pct').textContent = (conf * 100).toFixed(1) + '%';

    // 三维评分
    const scoreMap = {
      'score-metadata': data.scores.metadata,
      'score-spectrum': data.scores.spectrum,
      'score-statistical': data.scores.statistical,
    };
    for (const [id, val] of Object.entries(scoreMap)) {
      const el = document.getElementById(id);
      const barEl = document.getElementById(id + '-bar');
      if (el) el.textContent = (val * 100).toFixed(0) + '%';
      if (barEl) setTimeout(() => { barEl.style.width = (val * 100) + '%'; }, 200);
    }

    // 文件信息
    document.getElementById('file-name').textContent = data.filename;
    document.getElementById('file-size').textContent = formatBytes(data.file_size);
    document.getElementById('file-dims').textContent = `${data.image_width} × ${data.image_height}`;
    document.getElementById('file-time').textContent = data.analysis_time_ms.toFixed(0) + ' ms';

    // 关键发现
    const findingsContainer = document.getElementById('findings-list');
    findingsContainer.innerHTML = '';
    (data.key_findings || []).forEach(f => {
      const item = document.createElement('div');
      item.className = 'finding-item';
      item.innerHTML = `
        <span class="finding-icon">${f.icon}</span>
        <div class="finding-content">
          <div class="finding-title">${escapeHtml(f.title)}</div>
          <div class="finding-detail">${escapeHtml(f.detail)}</div>
        </div>
      `;
      findingsContainer.appendChild(item);
    });

    // 详情面板
    renderDetailTable('detail-metadata', data.metadata_detail);
    renderDetailTable('detail-spectrum', data.spectrum_detail);
    renderDetailTable('detail-statistical', data.statistical_detail);
  }

  function renderDetailTable(containerId, detail) {
    const tbody = document.getElementById(containerId);
    if (!tbody || !detail) return;
    tbody.innerHTML = '';
    const labels = {
      has_ai_signature: 'AI 签名', ai_tool_detected: '检测到的 AI 工具',
      has_c2pa: 'C2PA 标记', c2pa_marker_count: 'C2PA 标记数量',
      c2pa_markers: 'C2PA 标记类型', c2pa_offsets: 'C2PA 标记位置',
      c2pa_readable_snippets: 'C2PA 可读片段', c2pa_note: 'C2PA 说明',
      has_camera_info: '相机信息',
      has_gps: 'GPS 定位', has_datetime: '拍摄日期',
      software: '软件', ai_parameters: 'AI 参数',
      high_freq_ratio: '高频能量比', spectral_slope: '频谱斜率',
      periodicity_score: '周期性伪影', grid_artifact_score: '棋盘格伪影',
      synthid_detected: 'SynthID 水印', synthid_confidence: 'SynthID 置信度',
      synthid_phase_match: 'SynthID 相位匹配度', synthid_best_set: 'SynthID 载波组',
      synthid_cvr_noise: 'SynthID 载波噪声比', synthid_source: 'SynthID 检测来源',
      noise_std: '噪声标准差', noise_uniformity: '噪声均匀度',
      color_histogram_entropy: '色彩熵', edge_sharpness: '边缘锐度',
      texture_regularity: '纹理规律性', local_consistency: '局部一致性',
    };

    for (const [key, val] of Object.entries(detail)) {
      if (val === null || val === undefined) continue;
      const tr = document.createElement('tr');
      const label = labels[key] || key;
      let display = val;
      if (typeof val === 'boolean') display = val ? '✅ 是' : '❌ 否';
      else if (Array.isArray(val)) {
        display = val.length > 0
          ? val.map(item => typeof item === 'object' ? JSON.stringify(item) : String(item)).join('\n')
          : '无';
      }
      else if (typeof val === 'number') display = val.toFixed(4);
      tr.innerHTML = `<td>${escapeHtml(label)}</td><td>${escapeHtml(String(display))}</td>`;
      tbody.appendChild(tr);
    }
  }

  // 详情面板折叠
  document.querySelectorAll('.detail-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      btn.classList.toggle('open');
      const body = btn.nextElementSibling;
      body.classList.toggle('open');
    });
  });

  // 重新检测
  window.resetDetection = function() {
    resetUI();
  };

  function resetUI() {
    uploadSection.style.display = 'block';
    analyzingSection.classList.remove('active');
    resultSection.classList.remove('active');
    resultSection.style.display = 'none';
    fileInput.value = '';
    document.getElementById('confidence-fill').style.width = '0%';
  }

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i];
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
});
